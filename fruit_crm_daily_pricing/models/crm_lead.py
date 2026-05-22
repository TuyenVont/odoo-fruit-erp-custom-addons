from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    fruit_market_info_ids = fields.One2many(
        "fruit.crm.market.info",
        "lead_id",
        string="Fruit Market Information",
    )

    fruit_market_info_count = fields.Integer(
        string="Market Info Count",
        compute="_compute_fruit_market_info_count",
    )

    def _compute_fruit_market_info_count(self):
        for lead in self:
            lead.fruit_market_info_count = len(lead.fruit_market_info_ids)

    def action_view_fruit_market_info(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Fruit Market Information",
            "res_model": "fruit.crm.market.info",
            "view_mode": "list,form",
            "domain": [("lead_id", "=", self.id)],
            "context": {
                "default_lead_id": self.id,
                "default_partner_id": self.partner_id.id,
                "default_salesperson_id": self.user_id.id,
                "default_sales_team_id": self.team_id.id,
            },
        }