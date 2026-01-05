
from odoo import models, fields, api, SUPERUSER_ID


def _populate_expense_options(env):
    env['account.expense.option.line'].sudo().create_missing_from_move_line()


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _populate_expense_options(env)


class AccountExpenseOptionLine(models.Model):
    _name = 'account.expense.option.line'
    _description = 'Expense Options from Move Line Accounts'
    _order = 'account_id'
    _check_company_auto = True
    

    account_id = fields.Many2one(
        'account.account',
        string='Expense Account',
        required=True,
        ondelete='cascade'
    )
    option_selection = fields.Selection([
        ('include_expense', 'Include in Purchase'),
        ('show_expense_row', 'Show Separately'),
        ('none', 'Do Not Include'),
    ], string='Option', default="none")

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        readonly=True
    )

 

    _sql_constraints = [
        ('unique_account_company', 'unique(account_id, company_id)', 'Each account only once per company!'),
    ]

    @api.model
    def create_missing_from_move_line(self):
        companies = self.env['res.company'].search([])
        for company in companies:
            expense_accounts = self.env['account.move.line'].search([
                ('company_id', '=', company.id)
            ]).mapped('account_id')
            expense_accounts = expense_accounts.filtered(lambda acc: acc.account_type == 'expense')
            existing_accounts = self.search([
                ('company_id', '=', company.id)
            ]).mapped('account_id.id')

            for account in expense_accounts:
                if account.id not in existing_accounts:
                    self.create({
                        'account_id': account.id,
                        'company_id': company.id,
                    })


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def action_open_expense_option(self):
        self.env['account.expense.option.line'].create_missing_from_move_line()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Expense Account Options (From Journal)',
            'res_model': 'account.expense.option.line',
            'view_mode': 'tree',
        }



