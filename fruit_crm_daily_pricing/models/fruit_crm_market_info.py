<<<<<<< HEAD
import csv
import io
import requests
from odoo import api, fields, models
from odoo.exceptions import UserError
=======
from odoo import api, fields, models

>>>>>>> 4ed5e83b0c80b286361d414de98decf8ef1ea591

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

<<<<<<< HEAD
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
        
        # Tìm hoặc tạo một Opportunity ảo để gom nhóm dữ liệu bò cào
        lead_scraped = self.env['crm.lead'].search([('name', '=', 'Khảo sát giá sàn tự động')], limit=1)
        if not lead_scraped:
            lead_scraped = self.env['crm.lead'].create({
                'name': 'Khảo sát giá sàn tự động',
                'description': 'Gom nhóm dữ liệu giá thu thập tự động hàng ngày từ Co.op và BHX.'
            })

        for row in reader:
            sku = row.get('Mã SKU')
            ten_sp = row.get('Tên Sản Phẩm')
            gia_san = float(row.get('Giá Bán Hiện Tại', 0))
            nguon_sao = row.get('Nguồn Dữ Liệu', 'Thị trường')

            if not ten_sp or gia_san <= 0:
                continue

            # Tìm sản phẩm trong Odoo để lấy đúng ID liên kết
            product = self.env['product.product'].search([
                '|', 
                ('name', 'ilike', ten_sp), 
                ('default_code', '=', sku)
            ], limit=1)

            if product:
                # Tạo mới một dòng thông tin thị trường làm cơ sở phân tích dữ liệu CRM
                self.create({
                    'lead_id': lead_scraped.id,
                    'product_id': product.id,
                    'info_date': fields.Date.context_today(self),
                    'competitor_price': gia_san,
                    'region': nguon_sao,
                    'confidence': 100.0,
                    'note': f"Hệ thống tự động đồng bộ mã SKU: {sku} từ {nguon_sao}",
                    'state': 'draft'
                })
                created_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Đồng bộ thành công',
                'message': f'Đã tạo thành công {created_count} bản ghi phân tích thị trường từ GitHub!',
                'sticky': False,
            }
        }

=======
>>>>>>> 4ed5e83b0c80b286361d414de98decf8ef1ea591
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