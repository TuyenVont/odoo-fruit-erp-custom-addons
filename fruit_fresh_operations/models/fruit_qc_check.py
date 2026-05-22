from odoo import api, fields, models
from odoo.exceptions import UserError


class FruitQcCheck(models.Model):
    _name = "fruit.qc.check"
    _description = "Fruit QC Check"
    _order = "qc_date desc, id desc"

    name = fields.Char(string="QC No.", default="New", copy=False)
    qc_date = fields.Date(string="QC Date", default=fields.Date.context_today)

    picking_id = fields.Many2one(
        "stock.picking",
        string="Receipt",
        required=True,
        domain="[('picking_type_code', '=', 'incoming')]",
    )

    supplier_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        related="picking_id.partner_id",
        store=True,
        readonly=True,
    )

    product_id = fields.Many2one("product.product", string="Product", required=True)
    lot_id = fields.Many2one("stock.lot", string="Lot/Batch", required=True)

    received_qty = fields.Float(string="Received Qty", required=True)
    accepted_qty = fields.Float(string="Accepted Qty", required=True)
    rejected_qty = fields.Float(string="Rejected Qty", required=True)
    damaged_weight = fields.Float(string="Damaged Weight")

    qc_result = fields.Selection([
        ("passed", "Passed"),
        ("failed", "Failed"),
        ("partial", "Partial"),
    ], string="QC Result", required=True, default="passed")

    action_required = fields.Selection([
        ("stock", "Move accepted qty to stock"),
        ("return_supplier", "Return rejected qty to supplier"),
        ("wastage", "Record rejected qty as wastage"),
        ("recheck", "Recheck"),
    ], string="Action Required", default="wastage")

    accepted_location_id = fields.Many2one(
        "stock.location",
        string="Accepted Destination",
        help="Ví dụ: KTHCM/Stock",
    )

    rejected_location_id = fields.Many2one(
        "stock.location",
        string="Rejected/Damage Destination",
        help="Ví dụ: KHU/Stock/Khu Chờ Hủy",
    )

    inspector_id = fields.Many2one(
        "res.users",
        string="Inspector",
        default=lambda self: self.env.user,
    )

    note = fields.Text(string="QC Note")

    wastage_log_id = fields.Many2one(
        "fruit.wastage.log",
        string="Generated Wastage Log",
        readonly=True,
    )

    state = fields.Selection([
        ("draft", "Draft"),
        ("done", "Done"),
        ("cancelled", "Cancelled"),
    ], string="Status", default="draft")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("fruit.qc.check") or "QC/New"
        return super().create(vals_list)

    @api.constrains("received_qty", "accepted_qty", "rejected_qty")
    def _check_qty(self):
        for rec in self:
            if rec.accepted_qty < 0 or rec.rejected_qty < 0:
                raise UserError("Accepted Qty và Rejected Qty không được âm.")

            total = round(rec.accepted_qty + rec.rejected_qty, 2)
            received = round(rec.received_qty, 2)

            if total != received:
                raise UserError("Accepted Qty + Rejected Qty phải bằng Received Qty.")

    def action_confirm_qc(self):
        for rec in self:
            if rec.state != "draft":
                continue

            rec.lot_id.write({
                "x_qc_status": rec.qc_result,
                "x_qc_note": rec.note,
            })

            if rec.rejected_qty > 0:
                wastage = self.env["fruit.wastage.log"].create({
                    "date": rec.qc_date,
                    "qc_check_id": rec.id,
                    "picking_id": rec.picking_id.id,
                    "product_id": rec.product_id.id,
                    "lot_id": rec.lot_id.id,
                    "qty": rec.rejected_qty,
                    "reason_type": "qc_failed",
                    "note": "Generated from QC Check %s" % rec.name,
                })
                rec.wastage_log_id = wastage.id

            rec.state = "done"