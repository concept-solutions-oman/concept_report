from odoo import models, fields

class AccountAccount(models.Model):
    _inherit = 'account.account'

    is_active_custom = fields.Boolean(string='Option')
