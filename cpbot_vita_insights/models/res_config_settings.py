from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    cpbot_api_url = fields.Char(
        string='Vita Insights API URL',
        config_parameter='cpbot_vita_insights.api_url',
        help='Base URL of the Vita Care cpbot backend, e.g. https://your-app.onrender.com '
             '(no trailing slash). The widget will POST to {url}/odoo/ask.',
    )
    cpbot_api_token = fields.Char(
        string='Vita Insights API Token',
        config_parameter='cpbot_vita_insights.api_token',
        help='Long-lived Bearer JWT issued for this Vita Care tenant. '
             'Sent as "Authorization: Bearer <token>" on every request.',
    )
