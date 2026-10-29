# -*- coding: utf-8 -*-
{
    'name': 'CPBot RAG Assistant',
    'version': '15.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Embeds a general-purpose document Q&A chat assistant natively inside Odoo',
    'description': """
CPBot RAG Assistant
====================
Adds a native chat widget backed by a retrieval-augmented-generation (RAG)
document Q&A backend. Ask questions in Arabic or English and get answers
grounded in your organization's documents, with inline images or links
where the backend provides supporting media.

Features
--------
* Configurable backend API URL and Bearer token (Settings > General Settings > RAG Assistant)
* Top-level menu with a client action that opens the chat widget
* Keeps a running conversation (conversation_id) for the duration of the session
* Not tied to any specific company or tenant - install on any Odoo database
""",
    'author': 'CPBot',
    'website': 'https://cpbot.example.com',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/cpbot_menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'cpbot_rag_assistant/static/src/js/cpbot_rag_widget.js',
            'cpbot_rag_assistant/static/src/xml/cpbot_rag_widget.xml',
            'cpbot_rag_assistant/static/src/scss/cpbot_rag_widget.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
