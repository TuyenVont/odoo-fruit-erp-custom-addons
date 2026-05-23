import csv
import io
import json
import re
import unicodedata
import requests

from odoo import models, fields, api
from odoo.exceptions import UserError

GITHUB_CSV_URL = "https://raw.githubusercontent.com/TuyenVont/odoo-fruit-erp-custom-addons/main/data_daily/gia_trai_cay_tong_hop.csv"

class CrmLead(models.Model):
    _inherit = "crm.lead"

    fruit_market_info_ids = fields.One2many(
        "fruit.crm.market.info",
        "lead_id",
        string="Fruit Market Info"
    )

    fruit_market_info_count = fields.Integer(
        string="Fruit Market Info Count",
        compute="_compute_fruit_market_info_count"
    )

    # Lưu giá cũ JSON
    previous_prices = fields.Text("Previous Prices JSON")

    def _compute_fruit_market_info_count(self):
        for lead in self:
            lead.fruit_market_info_count = len(lead.fruit_market_info_ids)

    # Chuẩn hóa text
    def _normalize_text(self, text):
        if not text:
            return ""
        text = str(text).lower().strip()
        text = text.replace("đ", "d")
        text = unicodedata.normalize("NFD", text)
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        noise_words = {
            "kg","g","gr","gram","trai","hop","tui","vi",
            "loai","l1","rpl","vf","select","coop","co","op",
            "online","tu","khoang","tro","len","dong","goi",
            "mieng","nhap","khau","noi","dia","trung","my",
            "phap","nam","phi","uc","newzealand"
        }
        tokens = [t for t in text.split() if t not in noise_words and not t.isdigit()]
        return " ".join(tokens)

    # Lấy nhóm trái cây gốc
    def _extract_fruit_key(self, product_name):
        normalized_name = self._normalize_text(product_name)
        fruit_aliases = [
            ("thanh long", ["thanh long"]),
            ("dua luoi", ["dua luoi"]),
            ("dua hau", ["dua hau"]),
            ("dua gang", ["dua gang"]),
            ("dua le", ["dua le"]),
            ("dua xiem", ["dua xiem"]),
            ("chuoi", ["chuoi"]),
            ("buoi", ["buoi"]),
            ("cam", ["cam"]),
            ("tao", ["tao"]),
            ("oi", ["oi"]),
            ("xoai", ["xoai"]),
            ("man", ["man"]),
            ("le", ["le"]),
            ("quyt", ["quyt"]),
            ("mit", ["mit"]),
            ("sapoche", ["sapoche","sapo"]),
            ("bo", ["bo"]),
            ("coc", ["coc"]),
            ("thom", ["thom","khom"]),
            ("kiwi", ["kiwi"]),
            ("nho", ["nho"]),
            ("chanh day", ["chanh day"]),
            ("du du", ["du du"]),
            ("dao", ["dao"]),
        ]
        for canonical_key, aliases in fruit_aliases:
            for alias in aliases:
                if re.search(r"(^| )%s( |$)" % re.escape(alias), normalized_name):
                    return canonical_key
        tokens = normalized_name.split()
        return tokens[0] if tokens else False

    # Fuzzy match 0-1
    def _match_score(self, a, b):
        a = self._normalize_text(a)
        b = self._normalize_text(b)
        if not a or not b:
            return 0
        if a == b or a in b or b in a:
            return 1
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a, b).ratio()

    def sync_market_price_from_github(self):
        """Update Market Info theo keyword mềm, CSV chỉ cần tên hoặc từ khóa trái cây"""
        try:
            response = requests.get(GITHUB_CSV_URL, timeout=20)
            response.raise_for_status()
            text = response.content.decode("utf-8-sig")
        except Exception as e:
            raise UserError(f"Lỗi khi lấy CSV: {e}")

        reader = csv.DictReader(io.StringIO(text))
        price_groups = {}

        # Gom giá theo nhóm
        for row in reader:
            product_name = row.get("Tên Sản Phẩm") or row.get("product_name")
            price_raw = row.get("Giá Bán Hiện Tại") or row.get("market_price")
            if not product_name or not price_raw:
                continue
            try:
                price = float(str(price_raw).replace(",", "").replace(".", "").strip())
            except Exception:
                continue
            fruit_key = self._extract_fruit_key(product_name)
            if not fruit_key:
                continue
            price_groups.setdefault(fruit_key, []).append(price)

        if not price_groups:
            raise UserError("Không tìm thấy dữ liệu giá hợp lệ trong CSV.")

        market_price_by_key = {k: sum(v)/len(v) for k,v in price_groups.items() if v}

        ProductTemplate = self.env["product.product"].sudo().search([("active","=",True),("sale_ok","=",True)])
        match_threshold = 0.7
        total_updated_count = 0

        # FIX: Thêm vòng lặp `for lead in self:` để xử lý chuẩn Recordset của Odoo
        for lead in self:
            updated_count = 0
            previous_prices_dict = {}

            for product in ProductTemplate:
                product_key = self._extract_fruit_key(product.name)
                selected_price = False
                if product_key and product_key in market_price_by_key:
                    selected_price = market_price_by_key[product_key]
                else:
                    # fallback fuzzy
                    product_norm = self._normalize_text(product.name)
                    best_score = 0
                    for csv_key, csv_price in market_price_by_key.items():
                        score = self._match_score(csv_key, product_norm)
                        if score >= match_threshold and score > best_score:
                            best_score = score
                            selected_price = csv_price
                
                if selected_price:
                    # Lưu giá cũ
                    previous_prices_dict[str(product.id)] = product.list_price

                    # FIX: Cập nhật điều kiện search, chỉ lấy market info thuộc về lead hiện tại
                    info = self.env["fruit.crm.market.info"].search([
                        ("lead_id", "=", lead.id),  # <-- Rất quan trọng để không ghi đè dữ liệu của Lead khác
                        ("product_id", "=", product.id),
                        ("grade", "=", "grade_1"),
                        ("info_date", "=", fields.Date.today())
                    ], limit=1)
                    
                    # FIX: Bổ sung lead_id vào biến vals để hết lỗi Validation Error
                    vals = {
                        "lead_id": lead.id,  # <-- Sửa lỗi "Missing required value"
                        "product_id": product.id,
                        "grade": "grade_1",
                        "customer_target_price": selected_price,
                        "competitor_price": selected_price,
                        "info_date": fields.Date.today(),
                        "expected_qty": 0.0
                    }
                    if info:
                        info.write(vals)
                    else:
                        self.env["fruit.crm.market.info"].create(vals)
                    updated_count += 1

            # Gán giá trị JSON vào bản ghi lead đang xử lý
            lead.previous_prices = json.dumps(previous_prices_dict)
            total_updated_count += updated_count

        return {
            "type":"ir.actions.client",
            "tag":"display_notification",
            "params":{
                "title":"Sync Market Price",
                "message":f"Đã cập nhật {total_updated_count} sản phẩm Market Info từ CSV (không đổi Sales Price)",
                "type":"success",
                "sticky": False
            }
        }

    def restore_previous_prices(self):
        """Restore giá cũ từ JSON"""
        # FIX: Thêm vòng lặp for để tránh lỗi khi người dùng chọn nhiều Cơ hội cùng lúc
        for lead in self:
            if not lead.previous_prices:
                continue
            
            previous_prices_dict = json.loads(lead.previous_prices)
            for product_id, old_price in previous_prices_dict.items():
                self.env['product.product'].browse(int(product_id)).write({'list_price': old_price})
            
            lead.previous_prices = ""
            
        return {
            "type":"ir.actions.client",
            "tag":"display_notification",
            "params":{
                "title":"Restore Prices",
                "message":"Đã restore sản phẩm về giá cũ thành công.",
                "type":"success",
                "sticky": False
            }
        }