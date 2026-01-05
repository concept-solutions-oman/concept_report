from odoo import models, fields, api
from odoo.exceptions import UserError

class AccountPaymentReportV2(models.Model):
    _name = 'account.payment.report.v2'
    _description = 'Account Payment Report V2'
    _auto = False
    _order = 'date desc'

    date = fields.Date("Date")
    journal_id = fields.Many2one("account.journal", "Journal")
    partner_id = fields.Many2one("res.partner", "Partner")
    move_id = fields.Many2one("account.move", "Journal Entry")
    ref = fields.Char("Memo")
    debit = fields.Monetary("Debit")
    credit = fields.Monetary("Credit")
    currency_id = fields.Many2one('res.currency', string='Currency')
    company_id = fields.Many2one('res.company', string="Company")
    bank_reference = fields.Char(string="Bank Reference")
    cheque_reference = fields.Char(string="Cheque Reference")
    due_date = fields.Date(string="Due Date")
    partner_type = fields.Selection([
        ('customer', 'Customer'),
        ('supplier', 'Vendor')
    ], string='Partner Type')
    payment_id = fields.Many2one("account.payment")
    parent_state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted')
    ], string="State", readonly=True)

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS account_payment_report_v2 CASCADE")
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW account_payment_report_v2 AS (
                SELECT 
                    ap.id AS id,
                    ap.id AS payment_id,
                    am.date AS date,
                    am.journal_id AS journal_id,
                    ap.partner_id AS partner_id,
                    ap.move_id AS move_id,
                    am.state AS parent_state,
                    am.invoice_date_due AS due_date,
                    am.ref AS ref,
                    CASE 
                        WHEN ap.payment_type = 'inbound' THEN ap.amount
                        ELSE 0.0
                    END AS debit,
                    CASE 
                        WHEN ap.payment_type = 'outbound' THEN -ap.amount
                        ELSE 0.0
                    END AS credit,
                    ap.currency_id AS currency_id,
                    am.company_id AS company_id,
                   
                    ap.bank_reference AS bank_reference,
                    ap.cheque_reference AS cheque_reference,
                    CASE
                        WHEN rp.customer_rank > 0 THEN 'customer'
                        WHEN rp.supplier_rank > 0 THEN 'supplier'
                        ELSE NULL
                    END AS partner_type
                FROM account_payment ap
                JOIN account_move am ON ap.move_id = am.id
                JOIN res_partner rp ON ap.partner_id = rp.id
            )
        """)
