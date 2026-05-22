from collections import defaultdict
from odoo import api, fields, models
from odoo.exceptions import UserError


class FruitDailyPriceBoard(models.Model):
    _name = "fruit.daily.price.board"
    _description = "Fruit Daily Price Board"
    _order = "price_date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Board Name", default="New", copy=False)

    price_date = fields.Date(
        string="Price Date",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )

    sales_team_id = fields.Many2one(
        "crm.team",
        string="Sales Team",
        tracking=True,
    )

    target_margin_percent = fields.Float(
        string="Target Margin (%)",
        default=20.0,
        help="Biên lợi nhuận mục tiêu dùng để tính giá đề xuất.",
    )

    line_ids = fields.One2many(
        "fruit.daily.price.board.line",
        "board_id",
        string="Price Lines",
    )

    pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Generated Pricelist",
        readonly=True,
    )

    state = fields.Selection([
        ("draft", "Draft"),
        ("generated", "Generated"),
        ("confirmed", "Confirmed"),
        ("sent", "Sent to Sales"),
        ("applied", "Applied to Pricelist"),
        ("cancelled", "Cancelled"),
    ], string="Status", default="draft", tracking=True)

    note = fields.Text(string="Note")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.name == "New":
                rec.name = "Daily Fruit Price Board - %s" % rec.price_date
        return records

    def _get_demand_adjustment(self, total_qty):
        if total_qty >= 700:
            return 2000
        if total_qty >= 300:
            return 1000
        if total_qty >= 100:
            return 500
        return 0

    def _get_confidence_weighted_average(self, infos, field_name):
        total_weight = 0
        total_value = 0

        for info in infos:
            value = info[field_name]
            if not value:
                continue

            weight = max(info.confidence or 0, 1) / 100.0
            qty_weight = max(info.expected_qty or 0, 1)
            final_weight = weight * qty_weight

            total_value += value * final_weight
            total_weight += final_weight

        if not total_weight:
            return 0

        return total_value / total_weight

    def action_generate_from_crm(self):
        for board in self:
            domain = [
                ("info_date", "=", board.price_date),
                ("state", "=", "draft"),
            ]

            if board.sales_team_id:
                domain.append(("sales_team_id", "=", board.sales_team_id.id))

            infos = self.env["fruit.crm.market.info"].search(domain)

            if not infos:
                raise UserError("Không có thông tin thị trường CRM nào cho ngày này.")

            board.line_ids.unlink()

            grouped = defaultdict(lambda: self.env["fruit.crm.market.info"])

            for info in infos:
                key = (info.product_id.id, info.grade)
                grouped[key] |= info

            for (product_id, grade), group_infos in grouped.items():
                product = self.env["product.product"].browse(product_id)

                total_qty = sum(group_infos.mapped("expected_qty"))
                avg_target_price = self._get_confidence_weighted_average(
                    group_infos,
                    "customer_target_price",
                )
                avg_competitor_price = self._get_confidence_weighted_average(
                    group_infos,
                    "competitor_price",
                )

                current_cost = product.standard_price or 0
                base_price = current_cost * (1 + board.target_margin_percent / 100.0)
                demand_adjustment = self._get_demand_adjustment(total_qty)

                market_refs = [
                    p for p in [avg_target_price, avg_competitor_price]
                    if p and p > 0
                ]

                if market_refs:
                    market_reference = sum(market_refs) / len(market_refs)
                    suggested_price = (base_price * 0.6) + (market_reference * 0.4) + demand_adjustment
                else:
                    suggested_price = base_price + demand_adjustment

                self.env["fruit.daily.price.board.line"].create({
                    "board_id": board.id,
                    "product_id": product.id,
                    "grade": grade,
                    "total_crm_demand_qty": total_qty,
                    "avg_customer_target_price": avg_target_price,
                    "avg_competitor_price": avg_competitor_price,
                    "current_cost": current_cost,
                    "target_margin_percent": board.target_margin_percent,
                    "demand_adjustment": demand_adjustment,
                    "suggested_price": round(suggested_price, 0),
                    "final_price": round(suggested_price, 0),
                    "market_info_count": len(group_infos),
                    "note": "Generated from CRM market information.",
                })

                group_infos.write({
                    "state": "used",
                    "price_board_id": board.id,
                })

            board.state = "generated"

    def action_confirm(self):
        for board in self:
            if not board.line_ids:
                raise UserError("Bảng giá chưa có dòng giá.")
            board.state = "confirmed"

    def action_send_to_sales(self):
        for board in self:
            if board.state not in ["confirmed", "generated", "applied"]:
                raise UserError("Chỉ gửi bảng giá sau khi đã generate hoặc confirm.")

            board.state = "sent"

            message = "Daily Fruit Price Board %s đã sẵn sàng cho Sales Team." % board.name
            board.message_post(body=message)

            users = self.env["res.users"]

            if board.sales_team_id:
                if "member_ids" in board.sales_team_id._fields:
                    users |= board.sales_team_id.member_ids
                if board.sales_team_id.user_id:
                    users |= board.sales_team_id.user_id

            if not users:
                users = self.env.user

            for user in users:
                board.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=user.id,
                    summary="Daily Fruit Price Board Ready",
                    note=message,
                )

    def action_apply_to_pricelist(self):
        for board in self:
            if not board.line_ids:
                raise UserError("Không có dòng giá để apply vào Pricelist.")

            currency = self.env.company.currency_id

            pricelist = self.env["product.pricelist"].create({
                "name": "Fruit Daily Pricelist - %s" % board.price_date,
                "currency_id": currency.id,
            })

            for line in board.line_ids:
                self.env["product.pricelist.item"].create({
                    "pricelist_id": pricelist.id,
                    "applied_on": "0_product_variant",
                    "product_id": line.product_id.id,
                    "compute_price": "fixed",
                    "fixed_price": line.final_price,
                    "min_quantity": 0,
                    "date_start": board.price_date,
                    "date_end": board.price_date,
                })

            board.pricelist_id = pricelist.id
            board.state = "applied"

            board.message_post(
                body="Đã tạo Pricelist: %s" % pricelist.display_name
            )

            return {
                "type": "ir.actions.act_window",
                "name": "Generated Pricelist",
                "res_model": "product.pricelist",
                "res_id": pricelist.id,
                "view_mode": "form",
                "target": "current",
            }

    def action_cancel(self):
        for board in self:
            board.state = "cancelled"


class FruitDailyPriceBoardLine(models.Model):
    _name = "fruit.daily.price.board.line"
    _description = "Fruit Daily Price Board Line"
    _order = "product_id, grade"

    board_id = fields.Many2one(
        "fruit.daily.price.board",
        string="Price Board",
        required=True,
        ondelete="cascade",
    )

    product_id = fields.Many2one(
        "product.product",
        string="Fruit Product",
        required=True,
    )

    grade = fields.Selection([
        ("premium", "Premium"),
        ("grade_1", "Loại 1"),
        ("grade_2", "Loại 2"),
        ("export", "Xuất khẩu"),
        ("vietgap", "VietGAP"),
        ("reject", "Reject"),
    ], string="Grade", required=True)

    total_crm_demand_qty = fields.Float(string="Total CRM Demand Qty")
    avg_customer_target_price = fields.Float(string="Avg Customer Target Price")
    avg_competitor_price = fields.Float(string="Avg Competitor Price")

    current_cost = fields.Float(string="Current Cost")
    target_margin_percent = fields.Float(string="Target Margin (%)")
    demand_adjustment = fields.Float(string="Demand Adjustment")

    suggested_price = fields.Float(string="Suggested Price")
    final_price = fields.Float(string="Final Approved Price")

    margin_percent = fields.Float(
        string="Final Margin (%)",
        compute="_compute_margin_percent",
        store=True,
    )

    market_info_count = fields.Integer(string="CRM Info Count")
    note = fields.Char(string="Note")

    @api.depends("current_cost", "final_price")
    def _compute_margin_percent(self):
        for line in self:
            if line.current_cost:
                line.margin_percent = ((line.final_price - line.current_cost) / line.current_cost) * 100
            else:
                line.margin_percent = 0