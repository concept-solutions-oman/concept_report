from odoo import models, fields, api

class AgedReceivableReportLine(models.Model):
    _name = 'aged.receivable.report.line'
    _description = 'Aged Receivable Report Line'
    _auto = False
    _order = 'date desc'

    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    move_id = fields.Many2one('account.move', string='Entry Label', readonly=True)
    date = fields.Date(string='Due Date', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Journal', readonly=True)
    account_id = fields.Many2one('account.account', string='Account', readonly=True)

    not_due = fields.Monetary(string='Not Due', readonly=True)
    bucket_1_30 = fields.Monetary(string='1 - 30', readonly=True)
    bucket_31_60 = fields.Monetary(string='31 - 60', readonly=True)
    bucket_61_90 = fields.Monetary(string='61 - 90', readonly=True)
    bucket_91_120 = fields.Monetary(string='91 - 120', readonly=True)
    bucket_121_180 = fields.Monetary(string='121 - 180', readonly=True)
    bucket_180_plus = fields.Monetary(string='180+', readonly=True)
    total = fields.Monetary(string='Total', readonly=True)
    move_type = fields.Selection(related='move_id.move_type', store=True)
    invoice_date = fields.Date(string="Invoice Date")
    due_date = fields.Date(string="Due Date")
    currency_id = fields.Many2one('res.currency', string='Currency')
    company_id = fields.Many2one('res.company', string='Company')

    aging_bucket = fields.Selection([
        ('not_due', 'Not Due'),
        ('1_30', '1 - 30'),
        ('31_60', '31 - 60'),
        ('61_90', '61 - 90'),
        ('91_120', '91 - 120'),
        ('121_180', '121 - 180'),
        ('180_plus', '180+'),
    ], string='Aging Bucket', readonly=True)

    parent_state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted')
    ], string="State", readonly=True)


    @api.model
    def init(self):
        self.env.cr.execute("""DROP VIEW IF EXISTS aged_receivable_report_line CASCADE""")
        self.env.cr.execute("""
            CREATE VIEW aged_receivable_report_line AS (
                SELECT
                    aml.id as id,
                    aml.partner_id,
                    aml.move_id,
                    aml.date_maturity as date,
                    aml.journal_id,
                    aml.account_id,
                    aml.currency_id,
                    aml.company_id,
                    am.move_type,
                    am.invoice_date AS invoice_date,
                    am.invoice_date_due AS due_date,
                    am.state AS parent_state,
                    CASE WHEN aml.date_maturity > CURRENT_DATE THEN aml.amount_residual ELSE 0 END as not_due,
                    CASE WHEN CURRENT_DATE - aml.date_maturity BETWEEN 1 AND 30 THEN aml.amount_residual ELSE 0 END as bucket_1_30,
                    CASE WHEN CURRENT_DATE - aml.date_maturity BETWEEN 31 AND 60 THEN aml.amount_residual ELSE 0 END as bucket_31_60,
                    CASE WHEN CURRENT_DATE - aml.date_maturity BETWEEN 61 AND 90 THEN aml.amount_residual ELSE 0 END as bucket_61_90,
                    CASE WHEN CURRENT_DATE - aml.date_maturity BETWEEN 91 AND 120 THEN aml.amount_residual ELSE 0 END as bucket_91_120,
                    CASE WHEN CURRENT_DATE - aml.date_maturity BETWEEN 121 AND 180 THEN aml.amount_residual ELSE 0 END as bucket_121_180,
                    CASE WHEN CURRENT_DATE - aml.date_maturity > 180 THEN aml.amount_residual ELSE 0 END as bucket_180_plus,

                    CASE
                        WHEN aml.date_maturity > CURRENT_DATE THEN 'not_due'
                        WHEN CURRENT_DATE - aml.date_maturity BETWEEN 1 AND 30 THEN '1_30'
                        WHEN CURRENT_DATE - aml.date_maturity BETWEEN 31 AND 60 THEN '31_60'
                        WHEN CURRENT_DATE - aml.date_maturity BETWEEN 61 AND 90 THEN '61_90'
                        WHEN CURRENT_DATE - aml.date_maturity BETWEEN 91 AND 120 THEN '91_120'
                        WHEN CURRENT_DATE - aml.date_maturity BETWEEN 121 AND 180 THEN '121_180'
                        ELSE '180_plus'
                    END as aging_bucket,

                    aml.amount_residual as total

                FROM account_move_line aml
                JOIN account_account acc ON aml.account_id = acc.id
                JOIN account_move am ON aml.move_id = am.id
                WHERE
                    am.move_type IN ('out_invoice', 'out_refund', 'entry')
                    AND aml.amount_residual != 0
                   
                    AND aml.reconciled = false
                    AND acc.account_type = 'asset_receivable'
                    AND aml.partner_id IS NOT NULL
            );
        """)

