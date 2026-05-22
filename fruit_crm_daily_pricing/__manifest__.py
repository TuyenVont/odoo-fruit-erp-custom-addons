{
    "name": "Fruit CRM Daily Pricing",
    "version": "1.0",
    "summary": "Collect CRM market signals and generate daily fruit price boards for Sales",
    "category": "Sales/CRM",
    "author": "ERP Student Team",
    "depends": [
        "crm",
        "sale_management",
        "product",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/menu.xml",
        "views/crm_lead_views.xml",
        "views/fruit_crm_market_info_views.xml",
        "views/fruit_daily_price_board_views.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}