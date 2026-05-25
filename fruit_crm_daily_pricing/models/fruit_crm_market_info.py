import csv  # Bổ sung thư viện csv bị thiếu để tránh lỗi NameError
from email.mime import text
import io
import re
import unicodedata
import requests
from odoo import api, fields, models
from odoo.exceptions import UserError


class FruitCrmMarketInfo(models.Model):
    _name = "fruit.crm.market.info"
    _description = "Fruit CRM Market Information"
    _order = "info_date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Reference", default="New", copy=False)

    lead_id = fields.Many2one(
        "crm.lead",
        string="Opportunity",
        required=True,
        ondelete="cascade",
    )

    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        related="lead_id.partner_id",
        store=True,
        readonly=True,
    )

    salesperson_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        related="lead_id.user_id",
        store=True,
        readonly=True,
    )

    sales_team_id = fields.Many2one(
        "crm.team",
        string="Sales Team",
        related="lead_id.team_id",
        store=True,
        readonly=True,
    )

    info_date = fields.Date(
        string="Info Date",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )

    expected_delivery_date = fields.Date(
        string="Expected Delivery Date",
        tracking=True,
    )

    product_id = fields.Many2one(
        "product.product",
        string="Fruit Product",
        required=True,
        tracking=True,
    )

    grade = fields.Selection([
        ("premium", "Premium"),
        ("grade_1", "Loại 1"),
        ("grade_2", "Loại 2"),
        ("export", "Xuất khẩu"),
        ("vietgap", "VietGAP"),
        ("reject", "Reject"),
    ], string="Grade", required=True, default="grade_1", tracking=True)

    expected_qty = fields.Float(
        string="Expected Demand Qty",
        required=True,
        default=1.0,
        tracking=True,
    )

    uom_id = fields.Many2one(
        "uom.uom",
        string="UoM",
        related="product_id.uom_id",
        readonly=True,
        store=True,
    )

    customer_target_price = fields.Float(
        string="Customer Target Price",
        help="Giá khách kỳ vọng/mong muốn.",
        tracking=True,
    )

    competitor_price = fields.Float(
        string="Competitor / Market Price",
        help="Giá đối thủ hoặc giá thị trường ghi nhận từ CRM.",
        tracking=True,
    )

    market_demand_level = fields.Selection([
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("very_high", "Very High"),
    ], string="Market Demand Level", default="medium", tracking=True)

    region = fields.Char(string="Region / Market Area")

    confidence = fields.Float(
        string="Confidence (%)",
        default=80,
        help="Độ tin cậy của thông tin thị trường, từ 0 đến 100.",
    )

    note = fields.Text(string="Market Note")

    state = fields.Selection([
        ("draft", "Draft"),
        ("used", "Used in Price Board"),
        ("cancelled", "Cancelled"),
    ], string="Status", default="draft", tracking=True)

    price_board_id = fields.Many2one(
        "fruit.daily.price.board",
        string="Generated Price Board",
        readonly=True,
    )

    def _normalize_text(self, text):
        if not text:
            return ""

        text = str(text).replace("đ", "d").replace("Đ", "D")

        normalized = unicodedata.normalize("NFKD", text)
        no_diacritics = "".join(
            ch for ch in normalized if not unicodedata.combining(ch)
    )

        return re.sub(r"\s+", " ", no_diacritics).strip().lower()

    def _score_product_by_name(self, product, crawled_name):
        crawled_norm = self._normalize_text(crawled_name)
        product_norm = self._normalize_text(product.name or "")
        if not crawled_norm or not product_norm:
            return 0

        score = 0
        if crawled_norm == product_norm:
            score += 50
        if crawled_norm in product_norm:
            score += 20
        if product_norm in crawled_norm:
            score += 10

        crawled_tokens = crawled_norm.split()
        product_tokens = set(product_norm.split())

        for token in crawled_tokens:
            if token in product_norm:
                score += 8

        for token in product_tokens:
            if token in crawled_norm:
                score += 2

        if "cam sanh" in crawled_norm:
            if "cam sanh" in product_norm:
                score += 30
            if "cam xoan" in product_norm:
                score -= 30
        if "cam xoan" in crawled_norm:
            if "cam xoan" in product_norm:
                score += 30
            if "cam sanh" in product_norm:
                score -= 30

        has_5kg = "5kg" in crawled_norm or "5 kg" in crawled_norm
        product_has_5kg = "5kg" in product_norm or "5 kg" in product_norm
        if has_5kg and not product_has_5kg:
            score -= 40
        if "dong khay" in product_norm and "dong khay" not in crawled_norm:
            score -= 20
        if "nguyen trai" in product_norm and "nguyen trai" not in crawled_norm:
            score -= 20
        if "dong khay" in crawled_norm and "dong khay" in product_norm:
            score += 20
        if "nguyen trai" in crawled_norm and "nguyen trai" in product_norm:
            score += 20

        return score

    def action_sync_price_from_github(self):
        url = "https://raw.githubusercontent.com/TuyenVont/odoo-fruit-erp-custom-addons/main/data_daily/gia_trai_cay_tong_hop.csv"

        try:
            response = requests.get(url, timeout=15)
        except Exception as e:
            raise UserError(f"Không thể kết nối tới GitHub để lấy dữ liệu: {str(e)}")

        if response.status_code != 200:
            raise UserError("Tải file từ GitHub thất bại. Vui lòng kiểm tra lại đường dẫn link raw.")

        csv_data = io.StringIO(response.text)
        reader = csv.DictReader(csv_data)

        created_count = 0
        skipped_count = 0

        lead_scraped = self.env["crm.lead"].search([
            ("name", "=", "Khảo sát giá sàn tự động")
        ], limit=1)

        if not lead_scraped:
            lead_scraped = self.env["crm.lead"].create({
                "name": "Khảo sát giá sàn tự động",
                "description": "Gom nhóm dữ liệu giá thu thập tự động hàng ngày từ Co.op, BHX hoặc nguồn thị trường.",
            })

        for row in reader:
            row_clean = {
                str(k).strip().lower(): v
                for k, v in row.items()
                if k
            }

            sku = (
                row_clean.get("mã sku")
                or row_clean.get("sku")
                or row_clean.get("ma sku")
                or ""
            )

            ten_sp = (
                row_clean.get("tên sản phẩm")
                or row_clean.get("ten san pham")
                or row_clean.get("name")
                or ""
            )

            gia_san_raw = (
                row_clean.get("giá bán hiện tại")
                or row_clean.get("gia ban hien tai")
                or row_clean.get("price")
                or ""
            )

            nguon_san = (
                row_clean.get("nguồn dữ liệu")
                or row_clean.get("nguon du lieu")
                or row_clean.get("source")
                or "Thị trường"
            )

            try:
                gia_san = float(str(gia_san_raw).replace(",", "").strip()) if gia_san_raw else 0.0
            except ValueError:
                gia_san = 0.0

            if not ten_sp or gia_san <= 0:
                skipped_count += 1
                continue

            crawled_norm = self._normalize_text(ten_sp)
            tokens = [token for token in crawled_norm.split() if token]
            if not tokens:
                skipped_count += 1
                continue

            name_domain = []
            for token in tokens[:3]:
                if not name_domain:
                    name_domain.extend([("name", "ilike", token)])
                else:
                    name_domain = ["|", ("name", "ilike", token)] + name_domain

            domain = [("sale_ok", "=", True)]
            if name_domain:
                domain += name_domain

            products = self.env["product.product"].search(domain, limit=150)
            if not products:
                skipped_count += 1
                continue

            best_product = None
            best_score = -999
            for product in products:
                score = self._score_product_by_name(product, ten_sp)
                if score > best_score:
                    best_product = product
                    best_score = score

            if not best_product or best_score < 40:
                skipped_count += 1
                continue

            self.create({
                "lead_id": lead_scraped.id,
                "product_id": best_product.id,
                "grade": "grade_1",
                "info_date": fields.Date.context_today(self),
                "expected_delivery_date": fields.Date.context_today(self),
                "expected_qty": 1.0,
                "competitor_price": gia_san,
                "customer_target_price": gia_san,
                "market_demand_level": "medium",
                "region": nguon_san,
                "confidence": 100.0,
                "note": (
                    f"Sản phẩm crawl: {ten_sp}\n"
                    f"SKU tham khảo: {sku or 'N/A'}\n"
                    f"Product Odoo map: {best_product.name} (ID {best_product.id})\n"
                    f"Best score: {best_score}"
                ),
                "state": "draft",
            })
            created_count += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Đồng bộ hoàn tất",
                "message": (
                    f"Đã tạo {created_count} bản ghi Market Information. "
                    f"Bỏ qua {skipped_count} dòng không hợp lệ hoặc không tìm thấy sản phẩm phù hợp."
                ),
                "sticky": False,
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.name == "New":
                rec.name = "MI-%s-%s" % (
                    rec.info_date.strftime("%Y%m%d") if rec.info_date else "DATE",
                    rec.id,
                )
        return records