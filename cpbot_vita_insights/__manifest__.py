{
    'name': 'CPBot Vita Insights',
    'version': '15.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Embeds the Vita Insights (cpbot) AI chat assistant natively inside Odoo',
    'description': """
CPBot Vita Insights
====================
Adds a native chat widget backed by the Vita Care cpbot FastAPI backend.

Features
--------
* Configurable backend API URL and Bearer token (Settings > General Settings > Vita Insights)
* Top-level menu with a client action that opens the chat widget
* Ask questions in Arabic or English, get answers with optional chart/table data
""",
    'author': 'Vita Care',
    'website': 'https://vitacare.example.com',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/cpbot_menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'cpbot_vita_insights/static/src/js/cpbot_chat_widget.js',
            'cpbot_vita_insights/static/src/xml/cpbot_chat_widget.xml',
            'cpbot_vita_insights/static/src/scss/cpbot_chat_widget.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
