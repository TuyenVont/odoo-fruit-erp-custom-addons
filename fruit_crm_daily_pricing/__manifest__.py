{
    "name": "Fruit CRM Daily Pricing Sync",
    "version": "1.0",
    "category": "Sales",
    "summary": "Sync fruit market price from GitHub CSV to Odoo",
    "depends": ["crm", "product"],
    "data": [
        "views/crm_lead_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}