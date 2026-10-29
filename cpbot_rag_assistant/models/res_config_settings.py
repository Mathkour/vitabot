# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    cpbot_rag_api_url = fields.Char(
        string='RAG Assistant API URL',
        config_parameter='cpbot_rag_assistant.api_url',
        help='Base URL of the RAG document Q&A backend, e.g. https://your-app.onrender.com '
             '(no trailing slash). The widget will POST to {url}/ask.',
    )
    cpbot_rag_api_token = fields.Char(
        string='RAG Assistant API Token',
        config_parameter='cpbot_rag_assistant.api_token',
        help='Long-lived Bearer JWT for this backend. '
             'Sent as "Authorization: Bearer <token>" on every request.',
    )
