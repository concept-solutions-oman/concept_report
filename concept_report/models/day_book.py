from odoo import models, fields
from dateutil.relativedelta import relativedelta
from datetime import date

class DayBookEntry(models.Model):
    _name = 'day.book.entry'
    _description = 'Day Book Entry'
    _auto = False
    _order = 'date desc'

    date = fields.Date("Date", required=True)
    journal_id = fields.Many2one("account.journal", string="Journal", required=True)
    move_id = fields.Many2one("account.move", string="Move")
    move_name = fields.Char("Move Name")
    entry_label = fields.Char("Entry Label")
    partner_id = fields.Many2one("res.partner", string="Partner")
    debit = fields.Monetary(string="Debit")
    credit = fields.Monetary(string="Credit")
    balance = fields.Monetary(string="Balance")
    account_id = fields.Many2one("account.account", string="Account")
    company_id = fields.Many2one('res.company', string="Company")
    currency_id = fields.Many2one("res.currency", string="Currency", default=lambda self: self.env.company.currency_id)
    move_type = fields.Selection(related='move_id.move_type', store=True)
    invoice_date = fields.Date(string="Invoice Date")
    due_date = fields.Date(string="Due Date")

    parent_state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted')
    ], string="State", readonly=True)

    def init(self):
        self.env.cr.execute("""
            DROP VIEW IF EXISTS day_book_entry;
            CREATE OR REPLACE VIEW day_book_entry AS (
                SELECT
                    l.id AS id,
                    l.date AS date,
                    l.company_id AS company_id,
                    l.journal_id AS journal_id,
                    am.invoice_date AS invoice_date,
                    am.invoice_date_due AS due_date,
                    am.state AS parent_state,
                    l.move_id AS move_id,
                    am.name AS move_name,
                    l.name AS entry_label,
                    l.partner_id AS partner_id,
                    l.debit AS debit,
                    l.credit AS credit,
                    (l.debit - l.credit) AS balance,
                    l.account_id AS account_id,
                    l.company_currency_id AS currency_id,
                    am.move_type AS move_type
                FROM account_move_line l
                JOIN account_move am ON l.move_id = am.id
                JOIN account_account acc ON l.account_id = acc.id
                WHERE l.date IS NOT NULL
                  AND acc.account_type IN ('asset_receivable', 'liability_payable')
            );
        """)
