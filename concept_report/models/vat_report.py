import datetime
from odoo import models, fields, api
from datetime import date
from calendar import monthrange
from odoo.exceptions import ValidationError
import io
import base64
import xlsxwriter

class VatReportMonthlyLine(models.Model):
    _name = 'vat.report.monthly.line'
    _description = 'VAT Monthly Sales Breakdown Line'

    vat_report_id = fields.Many2one('vat.report', string='VAT Report', required=True, ondelete='cascade')
    month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'),
        ('4', 'April'), ('5', 'May'), ('6', 'June'),
        ('7', 'July'), ('8', 'August'), ('9', 'September'),
        ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string="Month", required=True)
    sales_with_vat = fields.Float(string="Sales with VAT", readonly=True, digits=(16, 3))
    sales_vat_output = fields.Float(string="VAT Output", readonly=True, digits=(16, 3))
    sales_without_vat = fields.Float(string="Sales with 0% VAT", readonly=True, digits=(16, 3))
    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env.company)
    @api.model
    def create(self, vals):
        if 'company_id' not in vals:
            vals['company_id'] = self.env.company.id
        return super().create(vals)



class VatReportCreditNoteLine(models.Model):
    _name = 'vat.report.credit.line'
    _description = 'VAT Monthly Credit Note Breakdown Line'

    vat_report_id = fields.Many2one('vat.report', string='VAT Report', required=True, ondelete='cascade')
    month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'),
        ('4', 'April'), ('5', 'May'), ('6', 'June'),
        ('7', 'July'), ('8', 'August'), ('9', 'September'),
        ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string="Month", required=True)

    credit_with_vat = fields.Float(string="Credit with VAT", readonly=True, digits=(16, 3))
    credit_vat_output = fields.Float(string="VAT Output", readonly=True, digits=(16, 3))
    credit_without_vat = fields.Float(string="Credit with 0% VAT", readonly=True, digits=(16, 3))
    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env.company)
    
    @api.model
    def create(self, vals):
        if 'company_id' not in vals:
            vals['company_id'] = self.env.company.id
        return super().create(vals)


class VatReport(models.Model):
    _name = 'vat.report'
    _description = 'VAT Report'

    start_date = fields.Date(string="Start Date", default=fields.Date.context_today)
    end_date = fields.Date(string="End Date", default=fields.Date.context_today)
    quarter_name = fields.Selection([('1', 'Q1'), ('2', 'Q2'), ('3', 'Q3'), ('4', 'Q4')], default='1', string="Quarter")
    year = fields.Integer(string='Year', default=lambda self: date.today().year)
    posted_items = fields.Boolean(string="Posted Items", default=True)

    sales_with_vat = fields.Float(string="Sales with VAT", readonly=True, digits=(16, 3))
    sales_vat_output = fields.Float(string="VAT Output", readonly=True, digits=(
        16, 3))
    sales_without_vat = fields.Float(string="Sales with 0% VAT", readonly=True, digits=(16, 3))

    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env.company)

    monthly_line_ids = fields.One2many('vat.report.monthly.line', 'vat_report_id', string="Sales Breakdown", readonly=True)
    credit_line_ids = fields.One2many('vat.report.credit.line', 'vat_report_id', string="Credit Breakdown", readonly=True)

    horizontal_table_html = fields.Html(string="Monthly Summary Table", readonly=True)
    purchase_table_html = fields.Html(string="Purchase Summary Table", readonly=True)
    expense_table_html = fields.Html(string="Expense Summary Table", readonly=True) # New field for expense table
    expense_details_table_html = fields.Html(string="Expense Details Summary Table", readonly=True)

    

    # tax_id=201017
    # tax_id_purchase=104041
    # tax_id_expense=104041 # Assuming the same VAT input account for expenses, adjust if different

    
    account_ids = fields.Many2many('account.account', string='VAT Accounts (Selected from Option)', 
                                   domain=[('is_active_custom', '=', True)])
    
    def _get_dynamic_tax_account_codes(self):
    # From active accounts user selected
        accounts = self.env['account.account'].search([('is_active_custom', '=', True)])
        return accounts.mapped('code')


    @api.onchange('year', 'quarter_name')
    def _compute_quarter_dates(self):
        for rec in self:
            if not rec.year or not rec.quarter_name:
                rec.start_date = False
                rec.end_date = False
                continue
            year = rec.year
            q = rec.quarter_name
            quarter_dates = {
                '1': (date(year, 1, 1), date(year, 3, 31)),
                '2': (date(year, 4, 1), date(year, 6, 30)),
                '3': (date(year, 7, 1), date(year, 9, 30)),
                '4': (date(year, 10, 1), date(year, 12, 31)),
            }
            dates = quarter_dates.get(q)
            if dates:
                rec.start_date, rec.end_date = dates
            rec.compute_all_values()
            rec._compute_monthly_breakdown()
            rec._render_horizontal_table()
            rec._render_purchase_table()
            rec._render_expense_table()
            rec._render_expense_details_table()

    @api.onchange('start_date', 'end_date')
    def _onchange_date(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.start_date > rec.end_date:
                raise ValidationError("Start Date must be earlier than End Date")
            rec.compute_all_values()
            rec._compute_monthly_breakdown()
            rec._render_horizontal_table()
            rec._render_purchase_table()
            rec._render_expense_table()
            rec._render_expense_details_table()

    def compute_all_values(self):
        for rec in self:
            rec.sales_with_vat = rec._compute_sales_for_period(rec.start_date, rec.end_date, True, 'out_invoice')
            rec.sales_without_vat = rec._compute_sales_for_period(rec.start_date, rec.end_date, False, 'out_invoice')
            rec.sales_vat_output = rec._compute_vat_output_for_period(rec.start_date, rec.end_date, 'out_invoice')

    def _compute_sales_for_period(self, start_date, end_date, with_vat, move_type):
        domain = [
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', end_date),
            ('move_id.move_type', '=', move_type),
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.company_id.id)

        ]
        if move_type in ['out_invoice', 'out_refund', 'in_invoice', 'in_refund']: # ADDED 'in_invoice', 'in_refund'
            domain.append(('company_id', '=', self.company_id.id))
        if with_vat:
            domain.append(('tax_ids.amount', '!=', 0))
        else:
            domain.append(('tax_ids.amount', '=', 0)) # it is important to select the tax 0% for calculation
        lines = self.env['account.move.line'].search(domain)
        if move_type in ['out_invoice', 'in_invoice']:
            return sum(line.credit - line.debit for line in lines)
        elif move_type in ['out_refund', 'in_refund']:
            return sum(line.debit - line.credit for line in lines)
        else:
            return 0.0

    def _compute_vat_output_for_period(self, start_date, end_date, move_type):
        domain = [
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', end_date),
            ('move_id.move_type', '=', move_type),
            ('parent_state', '=', 'posted'),
            ('account_id.code', 'in', self._get_dynamic_tax_account_codes())  # Adjust this to your VAT Output account ID
            
        ]
        if move_type in ['out_invoice', 'out_refund', 'in_invoice', 'in_refund']: # ADDED 'in_invoice', 'in_refund'
            domain.append(('company_id', '=', self.company_id.id))
        lines = self.env['account.move.line'].search(domain)
        if move_type == 'out_invoice':
            return sum(line.credit - line.debit for line in lines)
        elif move_type == 'out_refund':
            return sum(line.debit - line.credit for line in lines)
        else:
            return 0.0

    def _compute_monthly_breakdown(self):
        for rec in self:
            rec.monthly_line_ids = [(5, 0, 0)]
            rec.credit_line_ids = [(5, 0, 0)]
            months_by_quarter = {
                '1': [1, 2, 3],
                '2': [4, 5, 6],
                '3': [7, 8, 9],
                '4': [10, 11, 12],
            }
            month_list = months_by_quarter.get(rec.quarter_name, [])
            monthly_vals = []
            credit_vals = []
            for m in month_list:
                start_day = date(rec.year, m, 1)
                end_day = date(rec.year, m, monthrange(rec.year, m)[1])
                monthly_vals.append((0, 0, {
                    'month': str(m),
                    'sales_with_vat': rec._compute_sales_for_period(start_day, end_day, True, 'out_invoice'),
                    'sales_without_vat': rec._compute_sales_for_period(start_day, end_day, False, 'out_invoice'),
                    'sales_vat_output': rec._compute_vat_output_for_period(start_day, end_day, 'out_invoice'),
                }))
                credit_vals.append((0, 0, {
                    'month': str(m),
                    'credit_with_vat': rec._compute_sales_for_period(start_day, end_day, True, 'out_refund'),
                    'credit_without_vat': rec._compute_sales_for_period(start_day, end_day, False, 'out_refund'),
                    'credit_vat_output': rec._compute_vat_output_for_period(start_day, end_day, 'out_refund'),
                }))
            rec.monthly_line_ids = monthly_vals
            rec.credit_line_ids = credit_vals

    def _render_horizontal_table(self):
        for rec in self:
            months = [line.month for line in rec.monthly_line_ids]
            month_names = dict(self.env['vat.report.monthly.line']._fields['month'].selection)

            # Header rows (same)
            header_cells = "".join(f'<th colspan="2" style="text-align:center;">{month_names.get(m, m)}</th>' for m in months)
            header_html = f"<tr><th></th>{header_cells}</tr>"
            sub_header_cells = "".join('<th style="width: 80px;">Amount</th><th style="width: 80px;">VAT</th>' for _ in months)
            sub_header_html = f"<tr><th style='width:150px;'></th>{sub_header_cells}</tr>"

            def fmt(val):
                return f"{val:,.3f}" if val else "0.000"

            sales_with_vat_row = "<tr><td><b>Sales with VAT</b></td>"
            sales_without_vat_row = "<tr><td><b>Sales without VAT</b></td>"
            credit_with_vat_row = "<tr><td>Credit with VAT</td>"
            credit_without_vat_row = "<tr><td>Credit with 0% VAT</td>"

            # Initialize totals dictionary for each month: totals[month] = {'amount': 0, 'vat': 0}
            totals = {m: {'amount': 0.0, 'vat': 0.0} for m in months}

            for m in months:
                sales_line = rec.monthly_line_ids.filtered(lambda l: l.month == m)
                credit_line = rec.credit_line_ids.filtered(lambda l: l.month == m)

                # Sales with VAT
                sales_amount_vat = sales_line.sales_with_vat if sales_line else 0.0
                sales_vat = sales_line.sales_vat_output if sales_line else 0.0
                sales_with_vat_row += f"<td style='text-align:right;'>{fmt(sales_amount_vat)}</td><td style='text-align:right;'>{fmt(sales_vat)}</td>"

                # Sales without VAT (VAT always 0.0)
                sales_amount_no_vat = sales_line.sales_without_vat if sales_line else 0.0
                sales_without_vat_row += f"<td style='text-align:right;'>{fmt(sales_amount_no_vat)}</td><td style='text-align:right;'>0.00</td>"

                # Credit with VAT
                credit_amount_vat = credit_line.credit_with_vat if credit_line else 0.0
                credit_vat = credit_line.credit_vat_output if credit_line else 0.0
                credit_with_vat_row += f"<td style='text-align:right;'>{fmt(credit_amount_vat)}</td><td style='text-align:right;'>{fmt(credit_vat)}</td>"

                # Credit without VAT (VAT always 0.0)
                credit_amount_no_vat = credit_line.credit_without_vat if credit_line else 0.0
                credit_without_vat_row += f"<td style='text-align:right;'>{fmt(credit_amount_no_vat)}</td><td style='text-align:right;'>0.00</td>"

                # Calculate totals for this month:
                # Total Amount = (Sales with VAT + Sales without VAT) - (Credit with VAT + Credit without VAT)
                total_amount = (sales_amount_vat + sales_amount_no_vat) - (credit_amount_vat + credit_amount_no_vat)
                # Total VAT = (Sales VAT Output) - (Credit VAT Output)
                total_vat = sales_vat - credit_vat

                totals[m]['amount'] = total_amount
                totals[m]['vat'] = total_vat

            sales_with_vat_row += "</tr>"
            sales_without_vat_row += "</tr>"
            credit_with_vat_row += "</tr>"
            credit_without_vat_row += "</tr>"

            # Build total row
            total_row = "<tr style='font-weight:bold; background:#f0f0f0;'><td>Total</td>"
            for m in months:
                total_row += f"<td style='text-align:right;'>{fmt(totals[m]['amount'])}</td><td style='text-align:right;'>{fmt(totals[m]['vat'])}</td>"
            total_row += "</tr>"

            table_html = f"""
                <table class="table table-sm table-bordered o_list_table" style="width: 100%; text-align:center;">
                    <thead>
                        {header_html}
                        {sub_header_html}
                    </thead>
                    <tbody>
                        {sales_with_vat_row}
                        {sales_without_vat_row}
                        {credit_with_vat_row}
                        {credit_without_vat_row}
                        {total_row}
                    </tbody>
                </table>
            """
            rec.horizontal_table_html = table_html

    def _render_purchase_table(self):
        for rec in self:
            months = [line.month for line in rec.monthly_line_ids]
            month_names = dict(self.env['vat.report.monthly.line']._fields['month'].selection)

            header_cells = "".join(f'<th colspan="2" style="text-align:center;">{month_names.get(m, m)}</th>' for m in months)
            sub_header_cells = "".join('<th style="width: 80px;">Amount</th><th style="width: 80px;">VAT</th>' for _ in months)

            table_html = f"""
                <table class="table table-sm table-bordered o_list_table" style="width: 100%; text-align:center;">
                    <thead>
                        <tr><th></th>{header_cells}</tr>
                        <tr><th style='width:150px;'></th>{sub_header_cells}</tr>
                    </thead>
                    <tbody>
            """

            def fmt(val):
                return f"{val:,.3f}" if val else "0.000"

            regions = ['Oman', 'United Arab Emirates', 'Other']
            combined_region_totals = {m: {'amount': 0.0, 'vat': 0.0} for m in months}
            purchase_return_totals = {m: {'amount': 0.0, 'vat': 0.0} for m in months}

            def get_purchase_and_vat(month_num, region, move_type, with_vat=True):
                start_day = date(rec.year, month_num, 1)
                end_day = date(rec.year, month_num, monthrange(rec.year, month_num)[1])
                purchase_amount = rec._compute_purchase_by_region(start_day, end_day, region, move_type, with_vat=with_vat)
                vat_amount = rec._compute_vat_by_region(start_day, end_day, region, move_type) if with_vat else 0.0
                return purchase_amount, vat_amount

            expense_option_lines = self.env['account.expense.option.line'].search([
                ('company_id', '=', rec.company_id.id)
            ])

            expense_account_data = {}
            for exp_line in expense_option_lines:
                expense_account_data[exp_line.id] = {
                    'account': exp_line.account_id.name,
                    'option': exp_line.option_selection,
                    'monthly': {m: {'Oman': {'amount': 0.0, 'vat': 0.0},
                                    'United Arab Emirates': {'amount': 0.0, 'vat': 0.0},
                                    'Other': {'amount': 0.0, 'vat': 0.0}} for m in months}
                }
                for m_str in months:
                    m_int = int(m_str)
                    start_day = date(rec.year, m_int, 1)
                    end_day = date(rec.year, m_int, monthrange(rec.year, m_int)[1])

                    account_moves = self.env['account.move'].search([
                        ('move_type', '=', 'in_invoice'),
                        ('state', '=', 'posted'),
                        ('invoice_date', '>=', start_day),
                        ('invoice_date', '<=', end_day),
                        ('line_ids.account_id', '=', exp_line.account_id.id),
                        ('company_id', '=', rec.company_id.id)
                    ])

                    for move in account_moves:
                        partner_country = move.partner_id.country_id.name
                        region = partner_country if partner_country in regions else 'Other'
                        
                        # Sum expense amounts for this account only
                        expense_amount = sum(l.debit - l.credit for l in move.line_ids if l.account_id == exp_line.account_id)
                        
                        # Sum VAT only once per move (tax_line_id lines only)
                        vat_amount = sum(l.balance for l in move.line_ids if l.tax_line_id)

                        expense_account_data[exp_line.id]['monthly'][m_str][region]['amount'] += expense_amount
                        expense_account_data[exp_line.id]['monthly'][m_str][region]['vat'] += vat_amount

                    

            expense_return_account_data = {}
            for exp_line in expense_option_lines:
                expense_return_account_data[exp_line.id] = {
                    'account': exp_line.account_id.name,
                    'option': exp_line.option_selection,
                    'monthly': {m: {'Oman': {'amount': 0.0, 'vat': 0.0},
                                    'United Arab Emirates': {'amount': 0.0, 'vat': 0.0},
                                    'Other': {'amount': 0.0, 'vat': 0.0}} for m in months}
                }
                for m_str in months:
                    m_int = int(m_str)
                    start_day = date(rec.year, m_int, 1)
                    end_day = date(rec.year, m_int, monthrange(rec.year, m_int)[1])
                   

                    account_moves_return = self.env['account.move'].search([
                        ('move_type', '=', 'in_refund'),
                        ('state', '=', 'posted'),
                        ('invoice_date', '>=', start_day),
                        ('invoice_date', '<=', end_day),
                        ('line_ids.account_id', '=', exp_line.account_id.id),
                        ('company_id', '=', rec.company_id.id)
                    ])

                    for move in account_moves_return:
                        partner_country = move.partner_id.country_id.name
                        region = partner_country if partner_country in regions else 'Other'
                        # Total expense amount
                        expense_amount = sum(abs(l.debit - l.credit) for l in move.line_ids if l.account_id == exp_line.account_id)

                        vat_amount = sum(abs(l.balance) for l in move.line_ids if l.tax_line_id)

                        
                        expense_return_account_data[exp_line.id]['monthly'][m_str][region]['amount'] += expense_amount
                        expense_return_account_data[exp_line.id]['monthly'][m_str][region]['vat'] += vat_amount



            # Purchase Section
            for region in regions:
                row = f"<tr><td><b>Purchase from {region}</b></td>"
                for m_str in months:
                    m_int = int(m_str)
                    purchase_with_vat, vat_input = get_purchase_and_vat(m_int, region, 'in_invoice', with_vat=True)
                    purchase_no_vat, _ = get_purchase_and_vat(m_int, region, 'in_invoice', with_vat=False)

                    expense_amount = sum(data['monthly'][m_str][region]['amount']
                                        for data in expense_account_data.values()
                                        if data['option'] == 'include_expense')

                    expense_vat = sum(data['monthly'][m_str][region]['vat']
                                    for data in expense_account_data.values()
                                    if data['option'] == 'include_expense')
                    if region == "Oman":
                        total_amount = purchase_with_vat + purchase_no_vat + expense_amount
                    else:
                        total_amount = purchase_with_vat + expense_amount
                    total_vat = vat_input + expense_vat

                    row += f"<td style='text-align:right;'>{fmt(total_amount)}</td><td style='text-align:right;'>{fmt(total_vat)}</td>"
                    combined_region_totals[m_str]['amount'] += total_amount
                    combined_region_totals[m_str]['vat'] += total_vat
                row += "</tr>"
                table_html += row

                # After Oman, show show_separate_line totals
                if region == 'Oman':
                    for exp_data in expense_account_data.values():
                        if exp_data['option'] == 'show_expense_row':
                            expense_row = f"<tr><td style='padding-left: 20px;'>{exp_data['account']} (Expense)</td>"
                            for m_str in months:
                                total_amt = sum(exp_data['monthly'][m_str][r]['amount'] for r in regions)
                                total_vat = sum(exp_data['monthly'][m_str][r]['vat'] for r in regions)
                                expense_row += f"<td style='text-align:right;'>{fmt(total_amt)}</td><td style='text-align:right;'>{fmt(total_vat)}</td>"
                                combined_region_totals[m_str]['amount'] += total_amt
                                combined_region_totals[m_str]['vat'] += total_vat
                            expense_row += "</tr>"
                            table_html += expense_row

            total_row = "<tr style='font-weight:bold; background:#dff0d8;'><td>Total Purchase</td>"
            for m_str in months:
                total_amount = combined_region_totals[m_str]['amount']
                total_vat = combined_region_totals[m_str]['vat']
                total_row += f"<td style='text-align:right;'>{fmt(total_amount)}</td><td style='text-align:right;'>{fmt(total_vat)}</td>"
            total_row += "</tr>"
            table_html += total_row

            # Purchase Return Section
            for region in regions:
                row_return = f"<tr><td><b>Purchase return from {region}</b></td>"
                for m_str in months:
                    m_int = int(m_str)
                    purchase_return_vat, return_vat_input = get_purchase_and_vat(m_int, region, 'in_refund', with_vat=True)
                    purchase_return_no_vat, _ = get_purchase_and_vat(m_int, region, 'in_refund', with_vat=False)

                    expense_return_amount = sum(data['monthly'][m_str][region]['amount']
                                        for data in expense_return_account_data.values()
                                        if data['option'] == 'include_expense')

                    expense_return_vat = sum(data['monthly'][m_str][region]['vat']
                                    for data in expense_return_account_data.values()
                                    if data['option'] == 'include_expense')
                    
                    if region == "Oman":
                        total_amount = purchase_return_vat + purchase_return_no_vat + expense_return_amount
                    else:
                        total_amount = purchase_return_vat + expense_return_amount

                  
                    total_vat = return_vat_input + expense_return_vat
                   

                    row_return += f"<td style='text-align:right;'>{fmt(total_amount)}</td><td style='text-align:right;'>{fmt(total_vat)}</td>"
                    purchase_return_totals[m_str]['amount'] += total_amount
                    purchase_return_totals[m_str]['vat'] += total_vat
                row_return += "</tr>"
                table_html += row_return

                if region == 'Oman':
                    for exp_data in expense_return_account_data.values():
                        if exp_data['option'] == 'show_expense_row':
                            expense_row = f"<tr><td style='padding-left: 20px;'>{exp_data['account']} (Expense Return)</td>"
                            for m_str in months:
                                total_amt = sum(exp_data['monthly'][m_str][r]['amount'] for r in regions)
                                total_vat = sum(exp_data['monthly'][m_str][r]['vat'] for r in regions)
                                expense_row += f"<td style='text-align:right;'>{fmt(total_amt)}</td><td style='text-align:right;'>{fmt(total_vat)}</td>"
                                purchase_return_totals[m_str]['amount'] += total_amt
                                purchase_return_totals[m_str]['vat'] += total_vat
                            expense_row += "</tr>"
                            table_html += expense_row

            total_return_row = "<tr style='font-weight:bold; background:#dff0d8;'><td>Total Purchase Return</td>"
            for m_str in months:
                total_return_amount = purchase_return_totals[m_str]['amount']
                total_return_vat = purchase_return_totals[m_str]['vat']
                total_return_row += f"<td style='text-align:right;'>{fmt(total_return_amount)}</td><td style='text-align:right;'>{fmt(total_return_vat)}</td>"
            total_return_row += "</tr>"
            table_html += total_return_row

            net_total_row = "<tr style='font-weight:bold; background:#cce5ff;'><td>Total Purchase - Return</td>"
            for m_str in months:
                total_amount = combined_region_totals[m_str]['amount'] - purchase_return_totals[m_str]['amount']
                total_vat = combined_region_totals[m_str]['vat'] - purchase_return_totals[m_str]['vat']
                net_total_row += f"<td style='text-align:right;'>{fmt(total_amount)}</td><td style='text-align:right;'>{fmt(total_vat)}</td>"
            net_total_row += "</tr>"
            table_html += net_total_row

            table_html += "</tbody></table>"
            rec.purchase_table_html = table_html

    def _compute_purchase_by_region(self, start_date, end_date, region_name, move_type, with_vat=True):
        domain = [
            ('move_id.move_type', '=', move_type),
            ('move_id.state', '=', 'posted'),
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', end_date),
            ('account_id.account_type', '=', 'expense_direct_cost'),
            ('company_id', '=', self.company_id.id)
        ]

        # Handle the 'Other' region specifically
        if region_name == 'Other':
            domain.append(('move_id.partner_id.country_id.name', '!=', 'Oman'))
            domain.append(('move_id.partner_id.country_id.name', '!=', 'United Arab Emirates'))
            # You might also want to exclude partners with no country specified if 'Other' should strictly mean non-Oman/UAE countries.
            # domain.append(('move_id.partner_id.country_id', '!=', False))
        else:
            domain.append(('move_id.partner_id.country_id.name', '=', region_name))

        if region_name == 'Oman':
            if with_vat:
                domain.append(('tax_ids.amount', '!=', 0))
            else:
                # domain.append(('tax_ids.amount', '=', 0))
                domain.append('|')
                domain.append(('tax_ids', '=', False))
                domain.append(('tax_ids.amount', '=', 0))

        lines = self.env['account.move.line'].search(domain)
        # return sum(line.balance for line in lines)
        if move_type in ['in_invoice']:
            return sum(line.debit - line.credit for line in lines)
        elif move_type in ['in_refund']:
            return sum(line.credit - line.debit for line in lines)
        else:
            return 0.0

        
    def _compute_vat_by_region(self, start_date, end_date, region_name, move_type):
        tax_line_domain = [
            ('move_id.move_type', '=', move_type),
            ('move_id.state', '=', 'posted'),
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', end_date), 
            ('tax_line_id', '!=', False),
            ('company_id', '=', self.company_id.id)
        ]

        tax_codes = self._get_dynamic_tax_account_codes()
        if tax_codes:
            tax_line_domain.append(('account_id.code', 'in', tax_codes))
        else:
            # Do not search VAT at all if nothing is selected
            return 0.000  # e.g. tax paid account 116

        if region_name == 'Other':
            tax_line_domain.append(('move_id.partner_id.country_id.name', 'not in', ['Oman', 'United Arab Emirates']))
        else:
            tax_line_domain.append(('move_id.partner_id.country_id.name', '=', region_name))

        # Step 1: Get all tax lines
        tax_lines = self.env['account.move.line'].search(tax_line_domain)

        # Step 2: Keep only those where the same invoice has at least one expense line
        total_vat = 0.0
        for line in tax_lines:
            expense_lines = line.move_id.line_ids.filtered(lambda l: l.account_id.account_type == 'expense_direct_cost')
            if expense_lines:
        #         total_vat += line.debit - line.credit

        # return total_vat
    

                vat_amount = line.debit - line.credit
                if move_type == 'in_refund':
                    total_vat += abs(vat_amount) 
                else:
                    total_vat += vat_amount 

        return total_vat


    def _get_expense_totals_for_region(self, month, region):
        start_day = date(self.year, month, 1)
        end_day = date(self.year, month, monthrange(self.year, month)[1])

        expense_with_vat = self._compute_expense_by_region(start_day, end_day, region, 'in_invoice', with_vat=True)
        expense_without_vat = self._compute_expense_by_region(start_day, end_day, region, 'in_invoice', with_vat=False)
        vat_input = self._compute_vat_by_region_expense(start_day, end_day, region, 'in_invoice')

        return expense_with_vat, expense_without_vat, vat_input
   
# expense 
    def _render_expense_table(self):
        for rec in self:
            months = [line.month for line in rec.monthly_line_ids]
            month_names = dict(self.env['vat.report.monthly.line']._fields['month'].selection)

            header_cells = "".join(f'<th colspan="2" style="text-align:center;">{month_names.get(m, m)}</th>' for m in months)
            sub_header_cells = "".join('<th style="width: 80px;">Amount</th><th style="width: 80px;">VAT</th>' for _ in months)

            table_html = f"""
                <table class="table table-sm table-bordered o_list_table" style="width: 100%; text-align:center;">
                    <thead>
                        <tr><th></th>{header_cells}</tr>
                        <tr><th style='width:150px;'></th>{sub_header_cells}</tr>
                    </thead>
                    <tbody>
            """

            def fmt(val):
                return f"{val:,.3f}" if val else "0.000"

            regions = ['Oman', 'United Arab Emirates','Other']
            
            # This will store the combined totals for Oman and UAE
            combined_region_totals_expense = {m: {'amount': 0.0, 'vat': 0.0} for m in months}
            expense_return_totals = {m: {'amount': 0.0, 'vat': 0.0} for m in months}


            # Helper to compute expense and VAT for a region and VAT flag
            def get_expense_and_vat(month_num, region, move_type, with_vat=True):
                start_day = date(rec.year, month_num, 1)
                end_day = date(rec.year, month_num, monthrange(rec.year, month_num)[1])
                
                # expense amount
                expense_amount = rec._compute_expense_by_region(start_day, end_day, region, move_type, with_vat=with_vat)
                
                # VAT amount (only if with_vat is True)
                vat_amount = rec._compute_vat_by_region_expense(start_day, end_day, region, move_type) if with_vat else 0.0
                
                return expense_amount, vat_amount


            # Process Oman and UAE (combined for calculation, but still individual rows)
            for region in regions:
                
                
                if region == 'Oman':
                    expense_row = f"<tr><td><b>Expense from {region}</b></td>"
                    for m_str in months:
                        m_int = int(m_str)
                        expense_with_vat, expense_vat_input = get_expense_and_vat(m_int, region, 'in_invoice', with_vat=True)
                        expense_no_vat, _ = get_expense_and_vat(m_int, region, 'in_invoice', with_vat=False)
                        
                        total_expense = expense_with_vat + expense_no_vat
                        
                        expense_row += f"<td style='text-align:right;'>{fmt(total_expense)}</td><td style='text-align:right;'>{fmt(expense_vat_input)}</td>"
                        
                        combined_region_totals_expense[m_str]['amount'] += total_expense
                        combined_region_totals_expense[m_str]['vat'] += expense_vat_input
                    expense_row += "</tr>"
                    table_html += expense_row

                if  region == 'United Arab Emirates':
                    expense_row_ono_vat = f"<tr><td><b>Expense from {region}</b></td>"
                    for m_str in months:
                        m_int = int(m_str)  
                        expense_ono_vat, expense_ono_vat_input = get_expense_and_vat(m_int, region, 'in_invoice', with_vat=True)
                        expense_row_ono_vat += f"<td style='text-align:right;'>{fmt(expense_ono_vat)}</td><td style='text-align:right;'>{fmt(expense_ono_vat_input)}</td>"
                        combined_region_totals_expense[m_str]['amount'] += expense_ono_vat
                        combined_region_totals_expense[m_str]['vat'] += expense_ono_vat_input
                    expense_row_ono_vat += "</tr>"
                    table_html += expense_row_ono_vat


                if  region == 'Other':
                    expense_row_otno_vat = f"<tr><td><b>Expense other contries</b></td>"
                    for m_str in months:
                        m_int = int(m_str)  
                        expense_otno_vat, expense_otno_vat_input = get_expense_and_vat(m_int, region, 'in_invoice', with_vat=True)
                        expense_row_otno_vat += f"<td style='text-align:right;'>{fmt(expense_otno_vat)}</td><td style='text-align:right;'>{fmt(expense_otno_vat_input)}</td>"
                        combined_region_totals_expense[m_str]['amount'] += expense_otno_vat
                        combined_region_totals_expense[m_str]['vat'] += expense_otno_vat_input
                    expense_row_otno_vat += "</tr>"
                    table_html += expense_row_otno_vat
            # Add totals row (sum of Oman, Dubai, World)
            total_row = "<tr style='font-weight:bold; background:#dff0d8;'><td>Total Expense</td>"
            for m_str in months:
                # Sum of combined_region_totals_expense (Oman + UAE) + World totals
                total_amount = combined_region_totals_expense[m_str]['amount']
                total_vat = combined_region_totals_expense[m_str]['vat']
                total_row += f"<td style='text-align:right;'>{fmt(total_amount)}</td><td style='text-align:right;'>{fmt(total_vat)}</td>"
            total_row += "</tr>"
            table_html += total_row

            # -------- expense RETURNS SECTION --------
            

            for region in regions:
               

                if region == 'Oman':
                    row_return = f"<tr><td><b>Expense return from {region}</b></td>"
                    for m_str in months:
                        m_int = int(m_str)
                        expense_return_vat, return_vat_input = get_expense_and_vat(m_int, region, 'in_refund', with_vat=True)
                        expense_return_no_vat, _ = get_expense_and_vat(m_int, region, 'in_refund', with_vat=False)

                        total_return = expense_return_vat + expense_return_no_vat

                        row_return += f"<td style='text-align:right;'>{fmt(total_return)}</td><td style='text-align:right;'>{fmt(return_vat_input)}</td>"

                        expense_return_totals[m_str]['amount'] += total_return
                        expense_return_totals[m_str]['vat'] += return_vat_input
                    row_return += "</tr>"
                    table_html += row_return

                if region == 'United Arab Emirates':
                    row_uae_return = f"<tr><td><b>Expense return from {region}</b></td>"
                    for m_str in months:
                        m_int = int(m_str)
                        expense_return_uae, uae_vat_input = get_expense_and_vat(m_int, region, 'in_refund', with_vat=True)
                        row_uae_return += f"<td style='text-align:right;'>{fmt(expense_return_uae)}</td><td style='text-align:right;'>{fmt(uae_vat_input)}</td>"
                        expense_return_totals[m_str]['amount'] += expense_return_uae
                        expense_return_totals[m_str]['vat'] += uae_vat_input
                    row_uae_return += "</tr>"
                    table_html += row_uae_return

                if region == 'Other':
                    row_other_return = f"<tr><td><b>Expense return from other countries</b></td>"
                    for m_str in months:
                        m_int = int(m_str)
                        expense_return_other, other_vat_input = get_expense_and_vat(m_int, region, 'in_refund', with_vat=True)
                        row_other_return += f"<td style='text-align:right;'>{fmt(expense_return_other)}</td><td style='text-align:right;'>{fmt(other_vat_input)}</td>"
                        expense_return_totals[m_str]['amount'] += expense_return_other
                        expense_return_totals[m_str]['vat'] += other_vat_input
                    row_other_return += "</tr>"
                    table_html += row_other_return

            total_return_row = "<tr style='font-weight:bold; background:#dff0d8;'><td>Total Expense Return</td>"
            for m_str in months:
                total_return_amount = expense_return_totals[m_str]['amount']
                total_return_vat = expense_return_totals[m_str]['vat']
                total_return_row += f"<td style='text-align:right;'>{fmt(total_return_amount)}</td><td style='text-align:right;'>{fmt(total_return_vat)}</td>"
            total_return_row += "</tr>"
            table_html += total_return_row

            net_total_row = "<tr style='font-weight:bold; background:#cce5ff;'><td>Total Expense - Return</td>"
            for m_str in months:
                total_amount = combined_region_totals_expense[m_str]['amount'] - expense_return_totals[m_str]['amount']
                total_vat = combined_region_totals_expense[m_str]['vat'] - expense_return_totals[m_str]['vat']
                net_total_row += f"<td style='text-align:right;'>{fmt(total_amount)}</td><td style='text-align:right;'>{fmt(total_vat)}</td>"
            net_total_row += "</tr>"
            table_html += net_total_row
 

            

            table_html += "</tbody></table>"
            rec.expense_table_html = table_html

    def _compute_expense_by_region(self, start_date, end_date, region_name, move_type, with_vat=True):
        domain = [
            ('move_id.move_type', '=', move_type),
            ('move_id.state', '=', 'posted'),
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', end_date),
            ('account_id.account_type', '=', 'expense'),
            ('company_id', '=', self.company_id.id)
        ]

        # Handle the 'Other' region specifically
        if region_name == 'Other':
            domain.append(('move_id.partner_id.country_id.name', '!=', 'Oman'))
            domain.append(('move_id.partner_id.country_id.name', '!=', 'United Arab Emirates'))
            # You might also want to exclude partners with no country specified if 'Other' should strictly mean non-Oman/UAE countries.
            # domain.append(('move_id.partner_id.country_id', '!=', False))
        else:
            domain.append(('move_id.partner_id.country_id.name', '=', region_name))

        if region_name == 'Oman':
            if with_vat:
                domain.append(('tax_ids.amount', '!=', 0))
            else:
                # domain.append(('tax_ids.amount', '=', 0))
                domain.append('|')
                domain.append(('tax_ids', '=', False))
                domain.append(('tax_ids.amount', '=', 0))

        lines = self.env['account.move.line'].search(domain)
        # return sum(line.balance for line in lines)
        if move_type in ['in_invoice']:
            return sum(line.debit - line.credit for line in lines)
        elif move_type in ['in_refund']:
            return sum(line.credit - line.debit for line in lines)
        else:
            return 0.0

    
    def _compute_vat_by_region_expense(self, start_date, end_date, region_name, move_type):
        tax_line_domain = [
            ('move_id.move_type', '=', move_type),
            ('move_id.state', '=', 'posted'),
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', end_date), 
            ('tax_line_id', '!=', False),
            ('company_id', '=', self.company_id.id)
        ]

        if self._get_dynamic_tax_account_codes():
            tax_line_domain.append(('account_id.code', 'in', self._get_dynamic_tax_account_codes()))  # e.g. tax paid account 116

        if region_name == 'Other':
            tax_line_domain.append(('move_id.partner_id.country_id.name', 'not in', ['Oman', 'United Arab Emirates']))
        else:
            tax_line_domain.append(('move_id.partner_id.country_id.name', '=', region_name))

        # Step 1: Get all tax lines
        tax_lines = self.env['account.move.line'].search(tax_line_domain)

        # Step 2: Keep only those where the same invoice has at least one expense line
        total_vat = 0.0
        for line in tax_lines:
            expense_lines = line.move_id.line_ids.filtered(lambda l: l.account_id.account_type == 'expense')
            if expense_lines:
        #         total_vat += line.debit - line.credit

        # return total_vat
                
                vat_amount = line.debit - line.credit
                if move_type == 'in_refund':
                    total_vat += abs(vat_amount) 
                else:
                    total_vat += vat_amount 

        return total_vat




    #EXCEL
  
    def download_excel_report(self):
        self.ensure_one() # Ensures this method is called on a single record
        
        # Ensure data is computed before the report is generated
        self.compute_all_values()
        self._compute_monthly_breakdown() 

        # Return an action to redirect to the custom controller route
        return {
            'type': 'ir.actions.act_url',
            'url': f'/vat_report/export_excel/{self.id}', # This URL will be handled by your controller
            'target': 'self', # Opens in the same window/tab
        }

    
    def _export_combined_sales_sheet(self, sheet, workbook):
        header_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#D3D3D3'})
        subheader_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        data_format = workbook.add_format({'num_format': '#,##0.000', 'align': 'right', 'border': 1})
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'left'})
        # total_row_format = workbook.add_format({'bold': True, 'num_format': '#,##0.000', 'align': 'right', 'border': 1, 'bg_color': '#F0F0F0'})
        section_header_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#ADD8E6'}) # Light Blue
        total_row_format = workbook.add_format({'bold': True, 'num_format': '#,##0.000', 'align': 'right', 'border': 1, 'bg_color': '#DFF0D8'}) # Light Green
        net_total_row_format = workbook.add_format({'bold': True, 'num_format': '#,##0.000', 'align': 'right', 'border': 1, 'bg_color': '#CCE5FF'}) # Lighter Blue
        label_format = workbook.add_format({'bold': True, 'align': 'left', 'border': 1})

        sheet.merge_range('A1:B1', 'Sales & Sales Return Report', title_format)
        sheet.write('A2', f'Quarter: Q{self.quarter_name} - Year: {self.year}', title_format)

        months_by_quarter = {
            '1': [1, 2, 3], '2': [4, 5, 6],
            '3': [7, 8, 9], '4': [10, 11, 12],
        }
        months = [str(m) for m in months_by_quarter.get(self.quarter_name, [])]
        month_names = dict(self.env['vat.report.monthly.line']._fields['month'].selection)

        row_num = 4
        # Main Header Row (Empty cell for label, then merged month headers)
        sheet.write(row_num, 0, '', header_format)
        current_col = 1
        for m in months:
            sheet.merge_range(row_num, current_col, row_num, current_col + 1, month_names.get(m, m), header_format)
            current_col += 2
        
        row_num += 1
        # Sub-header Row (Empty cell for label, then 'Amount', 'VAT' for each month)
        sheet.write(row_num, 0, '', subheader_format)
        current_col = 1
        for _ in months:
            sheet.write(row_num, current_col, 'Amount', subheader_format)
            sheet.write(row_num, current_col + 1, 'VAT', subheader_format)
            current_col += 2
        
        row_num += 1 # Data starts here

        # --- SALES (out_invoice) ---
       
        sheet.write(row_num, 0, 'Sales', section_header_format) # Section Header
        sheet.merge_range(row_num, 1, row_num, len(months)*2, '', section_header_format) # Merge cells for the section header
        row_num += 1

        sales_section_totals_amount = {m: 0.0 for m in months}
        sales_section_totals_vat = {m: 0.0 for m in months}

        # Sales with VAT
        sheet.write(row_num, 0, 'Sales with VAT', label_format)
        current_col = 1
        for m in months:
            sales_line = self.monthly_line_ids.filtered(lambda l: l.month == m)
            amount = sales_line.sales_with_vat if sales_line else 0.0
            vat = sales_line.sales_vat_output if sales_line else 0.0
            sheet.write(row_num, current_col, amount, data_format)
            sheet.write(row_num, current_col + 1, vat, data_format)
            sales_section_totals_amount[m] += amount
            sales_section_totals_vat[m] += vat
            current_col += 2
        row_num += 1

        # Sales without VAT
        sheet.write(row_num, 0, 'Sales without VAT', label_format)
        current_col = 1
        for m in months:
            sales_line = self.monthly_line_ids.filtered(lambda l: l.month == m)
            amount = sales_line.sales_without_vat if sales_line else 0.0
            vat = 0.0 # Sales without VAT means no VAT
            sheet.write(row_num, current_col, amount, data_format)
            sheet.write(row_num, current_col + 1, vat, data_format)
            sales_section_totals_amount[m] += amount
            current_col += 2
        row_num += 1

        # Total Sales Row
        sheet.write(row_num, 0, 'Total Sales', total_row_format)
        current_col = 1
        for m in months:
            sheet.write(row_num, current_col, sales_section_totals_amount[m], total_row_format)
            sheet.write(row_num, current_col + 1, sales_section_totals_vat[m], total_row_format)
            current_col += 2
        row_num += 2 # Add an extra row for spacing before returns


        # --- SALES RETURNS (out_refund) ---
        sheet.write(row_num, 0, 'Sales Returns', section_header_format) # Section Header
        sheet.merge_range(row_num, 1, row_num, len(months)*2, '', section_header_format)
        row_num += 1

        returns_section_totals_amount = {m: 0.0 for m in months}
        returns_section_totals_vat = {m: 0.0 for m in months}

        # Sales Return with VAT
        sheet.write(row_num, 0, 'Sales Return with VAT', label_format)
        current_col = 1
        for m in months:
            credit_line = self.credit_line_ids.filtered(lambda l: l.month == m)
            amount = credit_line.credit_with_vat if credit_line else 0.0
            vat = credit_line.credit_vat_output if credit_line else 0.0
            sheet.write(row_num, current_col, amount, data_format)
            sheet.write(row_num, current_col + 1, vat, data_format)
            returns_section_totals_amount[m] += amount
            returns_section_totals_vat[m] += vat
            current_col += 2
        row_num += 1

        # Sales Return without VAT
        sheet.write(row_num, 0, 'Sales Return without VAT', label_format)
        current_col = 1
        for m in months:
            credit_line = self.credit_line_ids.filtered(lambda l: l.month == m)
            amount = credit_line.credit_without_vat if credit_line else 0.0
            vat = 0.0 # Sales Return without VAT means no VAT
            sheet.write(row_num, current_col, amount, data_format)
            sheet.write(row_num, current_col + 1, vat, data_format)
            returns_section_totals_amount[m] += amount
            current_col += 2
        row_num += 1

        # Total Sales Return Row
        sheet.write(row_num, 0, 'Total Sales Return', total_row_format)
        current_col = 1
        for m in months:
            sheet.write(row_num, current_col, returns_section_totals_amount[m], total_row_format)
            sheet.write(row_num, current_col + 1, returns_section_totals_vat[m], total_row_format)
            current_col += 2
        row_num += 2 # Add an extra row for spacing

        # Net Total Sales Row (Total Sales - Total Sales Returns)
        sheet.write(row_num, 0, 'Net Total Sales', net_total_row_format)
        current_col = 1
        for m in months:
            net_amount = sales_section_totals_amount[m] - returns_section_totals_amount[m]
            net_vat = sales_section_totals_vat[m] - returns_section_totals_vat[m]
            sheet.write(row_num, current_col, net_amount, net_total_row_format)
            sheet.write(row_num, current_col + 1, net_vat, net_total_row_format)
            current_col += 2
        row_num += 1

        # Adjust column widths
        sheet.set_column(0, 0, 45) # Wider for labels
        for i in range(1, len(months) * 2 + 1):
            sheet.set_column(i, i, 15)
    
    def _export_combined_purchase_sheet(self, sheet, workbook):
        from calendar import monthrange
        from datetime import date

        # --- Styles ---
        header_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#D3D3D3'})
        subheader_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        data_format = workbook.add_format({'num_format': '#,##0.000', 'align': 'right', 'border': 1})
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'left'})
        section_header_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#ADD8E6'})
        total_row_format = workbook.add_format({'bold': True, 'num_format': '#,##0.000', 'align': 'right', 'border': 1, 'bg_color': '#DFF0D8'})
        net_total_row_format = workbook.add_format({'bold': True, 'num_format': '#,##0.000', 'align': 'right', 'border': 1, 'bg_color': '#CCE5FF'})
        label_format = workbook.add_format({'bold': True, 'align': 'left', 'border': 1})

        # --- Header ---
        sheet.merge_range('A1:B1', 'Purchase Report', title_format)
        sheet.write('A2', f'Quarter: Q{self.quarter_name} - Year: {self.year}', title_format)

        months_by_quarter = {'1': [1, 2, 3], '2': [4, 5, 6], '3': [7, 8, 9], '4': [10, 11, 12]}
        months = [str(m) for m in months_by_quarter.get(self.quarter_name, [])]
        month_names = dict(self.env['vat.report.monthly.line']._fields['month'].selection)

        # --- Columns ---
        row_num = 4
        sheet.write(row_num, 0, '', header_format)
        current_col = 1
        for m in months:
            sheet.merge_range(row_num, current_col, row_num, current_col + 1, month_names.get(m, m), header_format)
            current_col += 2
        row_num += 1
        sheet.write(row_num, 0, '', subheader_format)
        current_col = 1
        for _ in months:
            sheet.write(row_num, current_col, 'Amount', subheader_format)
            sheet.write(row_num, current_col + 1, 'VAT', subheader_format)
            current_col += 2
        row_num += 1

        # --- Helpers ---
        def get_data_for_excel(month_num, region, move_type, with_vat=True):
            start_day = date(self.year, month_num, 1)
            end_day = date(self.year, month_num, monthrange(self.year, month_num)[1])
            amount = self._compute_purchase_by_region(start_day, end_day, region, move_type, with_vat=with_vat)
            vat = self._compute_vat_by_region(start_day, end_day, region, move_type) if with_vat else 0.0
            return amount, vat

        # --- Collect Expense Data ---
        expense_option_lines = self.env['account.expense.option.line'].search([('company_id', '=', self.company_id.id)])
        regions = ['Oman', 'United Arab Emirates', 'Other']
        expense_account_data = {}
        expense_return_account_data = {}

        for exp_line in expense_option_lines:
            account_name = exp_line.account_id.name
            option = exp_line.option_selection
            expense_account_data[exp_line.id] = {'account': account_name, 'option': option, 'monthly': {m: {r: {'amount': 0.0, 'vat': 0.0} for r in regions} for m in months}}
            expense_return_account_data[exp_line.id] = {'account': account_name, 'option': option, 'monthly': {m: {r: {'amount': 0.0, 'vat': 0.0} for r in regions} for m in months}}

            for m_str in months:
                m_int = int(m_str)
                start_day = date(self.year, m_int, 1)
                end_day = date(self.year, m_int, monthrange(self.year, m_int)[1])

                account_moves = self.env['account.move'].search([
                    ('move_type', '=', 'in_invoice'), ('state', '=', 'posted'),
                    ('invoice_date', '>=', start_day), ('invoice_date', '<=', end_day),
                    ('line_ids.account_id', '=', exp_line.account_id.id),
                    ('company_id', '=', self.company_id.id)
                ])
                for move in account_moves:
                    region = move.partner_id.country_id.name if move.partner_id.country_id.name in regions else 'Other'
                    expense_amount = sum(l.debit - l.credit for l in move.line_ids if l.account_id == exp_line.account_id)
                    vat_amount = sum(l.balance for l in move.line_ids if l.tax_line_id)
                    expense_account_data[exp_line.id]['monthly'][m_str][region]['amount'] += expense_amount
                    expense_account_data[exp_line.id]['monthly'][m_str][region]['vat'] += vat_amount

                account_moves_return = self.env['account.move'].search([
                    ('move_type', '=', 'in_refund'), ('state', '=', 'posted'),
                    ('invoice_date', '>=', start_day), ('invoice_date', '<=', end_day),
                    ('line_ids.account_id', '=', exp_line.account_id.id),
                    ('company_id', '=', self.company_id.id)
                ])
                for move in account_moves_return:
                    region = move.partner_id.country_id.name if move.partner_id.country_id.name in regions else 'Other'
                    expense_amount = sum(abs(l.debit - l.credit) for l in move.line_ids if l.account_id == exp_line.account_id)
                    vat_amount = sum(abs(l.balance) for l in move.line_ids if l.tax_line_id)
                    expense_return_account_data[exp_line.id]['monthly'][m_str][region]['amount'] += expense_amount
                    expense_return_account_data[exp_line.id]['monthly'][m_str][region]['vat'] += vat_amount

        # --- PURCHASES ---
        sheet.write(row_num, 0, 'Purchases', section_header_format)
        sheet.merge_range(row_num, 1, row_num, len(months) * 2, '', section_header_format)
        row_num += 1

        purchase_section_totals_amount = {m: 0.0 for m in months}
        purchase_section_totals_vat = {m: 0.0 for m in months}

        for region in regions:
            sheet.write(row_num, 0, f'Purchase from {region}', label_format)
            current_col = 1
            for m_str in months:
                m_int = int(m_str)
                amt_vat, vat = get_data_for_excel(m_int, region, 'in_invoice', with_vat=True)
                amt_no_vat, _ = get_data_for_excel(m_int, region, 'in_invoice', with_vat=False)

                expense_amount = sum(d['monthly'][m_str][region]['amount'] for d in expense_account_data.values() if d['option'] == 'include_expense')
                expense_vat = sum(d['monthly'][m_str][region]['vat'] for d in expense_account_data.values() if d['option'] == 'include_expense')

                if region == 'Oman':
                    total_amount = amt_vat + amt_no_vat + expense_amount
                    total_vat = vat + expense_vat
                else:
                    total_amount = amt_vat + expense_amount
                    total_vat = vat + expense_vat

                sheet.write(row_num, current_col, total_amount, data_format)
                sheet.write(row_num, current_col + 1, total_vat, data_format)
                purchase_section_totals_amount[m_str] += total_amount
                purchase_section_totals_vat[m_str] += total_vat
                current_col += 2
            row_num += 1

            if region == 'Oman':
                for exp_data in expense_account_data.values():
                    if exp_data['option'] == 'show_expense_row':
                        sheet.write(row_num, 0, f"{exp_data['account']} (Expense)", label_format)
                        current_col = 1
                        for m_str in months:
                            total_amt = sum(exp_data['monthly'][m_str][r]['amount'] for r in regions)
                            total_vat = sum(exp_data['monthly'][m_str][r]['vat'] for r in regions)
                            sheet.write(row_num, current_col, total_amt, data_format)
                            sheet.write(row_num, current_col + 1, total_vat, data_format)
                            purchase_section_totals_amount[m_str] += total_amt
                            purchase_section_totals_vat[m_str] += total_vat
                            current_col += 2
                        row_num += 1

        sheet.write(row_num, 0, 'Total Purchases', total_row_format)
        current_col = 1
        for m_str in months:
            sheet.write(row_num, current_col, purchase_section_totals_amount[m_str], total_row_format)
            sheet.write(row_num, current_col + 1, purchase_section_totals_vat[m_str], total_row_format)
            current_col += 2
        row_num += 2

        # --- PURCHASE RETURNS ---
        sheet.write(row_num, 0, 'Purchase Returns', section_header_format)
        sheet.merge_range(row_num, 1, row_num, len(months) * 2, '', section_header_format)
        row_num += 1

        returns_section_totals_amount = {m: 0.0 for m in months}
        returns_section_totals_vat = {m: 0.0 for m in months}

        for region in regions:
            sheet.write(row_num, 0, f'Purchase Return from {region}', label_format)
            current_col = 1
            for m_str in months:
                m_int = int(m_str)
                amt_vat, vat = get_data_for_excel(m_int, region, 'in_refund', with_vat=True)
                amt_no_vat, _ = get_data_for_excel(m_int, region, 'in_refund', with_vat=False)

                expense_amount = sum(d['monthly'][m_str][region]['amount'] for d in expense_return_account_data.values() if d['option'] == 'include_expense')
                expense_vat = sum(d['monthly'][m_str][region]['vat'] for d in expense_return_account_data.values() if d['option'] == 'include_expense')

                if region == 'Oman':
                    total_amount = amt_vat + amt_no_vat + expense_amount
                    total_vat = vat + expense_vat
                else:
                    total_amount = amt_vat + expense_amount
                    total_vat = vat + expense_vat

                sheet.write(row_num, current_col, total_amount, data_format)
                sheet.write(row_num, current_col + 1, total_vat, data_format)
                returns_section_totals_amount[m_str] += total_amount
                returns_section_totals_vat[m_str] += total_vat
                current_col += 2
            row_num += 1

            if region == 'Oman':
                for exp_data in expense_return_account_data.values():
                    if exp_data['option'] == 'show_expense_row':
                        sheet.write(row_num, 0, f"{exp_data['account']} (Expense Return)", label_format)
                        current_col = 1
                        for m_str in months:
                            total_amt = sum(exp_data['monthly'][m_str][r]['amount'] for r in regions)
                            total_vat = sum(exp_data['monthly'][m_str][r]['vat'] for r in regions)
                            sheet.write(row_num, current_col, total_amt, data_format)
                            sheet.write(row_num, current_col + 1, total_vat, data_format)
                            returns_section_totals_amount[m_str] += total_amt
                            returns_section_totals_vat[m_str] += total_vat
                            current_col += 2
                        row_num += 1

        sheet.write(row_num, 0, 'Total Purchase Returns', total_row_format)
        current_col = 1
        for m_str in months:
            sheet.write(row_num, current_col, returns_section_totals_amount[m_str], total_row_format)
            sheet.write(row_num, current_col + 1, returns_section_totals_vat[m_str], total_row_format)
            current_col += 2
        row_num += 2

        # --- NET TOTAL ---
        sheet.write(row_num, 0, 'Net Total Purchase', net_total_row_format)
        current_col = 1
        for m_str in months:
            net_amount = purchase_section_totals_amount[m_str] - returns_section_totals_amount[m_str]
            net_vat = purchase_section_totals_vat[m_str] - returns_section_totals_vat[m_str]
            sheet.write(row_num, current_col, net_amount, net_total_row_format)
            sheet.write(row_num, current_col + 1, net_vat, net_total_row_format)
            current_col += 2
        row_num += 1

        sheet.set_column(0, 0, 45)
        for i in range(1, len(months) * 2 + 1):
            sheet.set_column(i, i, 15)

    def _export_combined_expense_data1(self, sheet, workbook):
        header_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#D3D3D3'})
        subheader_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        data_format = workbook.add_format({'num_format': '#,##0.000', 'align': 'right', 'border': 1})
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'left'})
        section_header_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#ADD8E6'}) # Light Blue
        total_row_format = workbook.add_format({'bold': True, 'num_format': '#,##0.000', 'align': 'right', 'border': 1, 'bg_color': '#DFF0D8'}) # Light Green
        net_total_row_format = workbook.add_format({'bold': True, 'num_format': '#,##0.000', 'align': 'right', 'border': 1, 'bg_color': '#CCE5FF'}) # Lighter Blue
        label_format = workbook.add_format({'bold': True, 'align': 'left', 'border': 1})

        sheet.merge_range('A1:B1', 'Expense Report', title_format)
        sheet.write('A2', f'Quarter: Q{self.quarter_name} - Year: {self.year}', title_format)

        months_by_quarter = {
            '1': [1, 2, 3], '2': [4, 5, 6],
            '3': [7, 8, 9], '4': [10, 11, 12],
        }
        months = [str(m) for m in months_by_quarter.get(self.quarter_name, [])]
        month_names = dict(self.env['vat.report.monthly.line']._fields['month'].selection)

        row_num = 4
        sheet.write(row_num, 0, '', header_format)
        current_col = 1
        for m in months:
            sheet.merge_range(row_num, current_col, row_num, current_col + 1, month_names.get(m, m), header_format)
            current_col += 2

        row_num += 1
        sheet.write(row_num, 0, '', subheader_format)
        current_col = 1
        for _ in months:
            sheet.write(row_num, current_col, 'Amount', subheader_format)
            sheet.write(row_num, current_col + 1, 'VAT', subheader_format)
            current_col += 2

        row_num += 1

        def get_data_for_excel(month_num, region, move_type, with_vat=True):
            start_day = date(self.year, month_num, 1)
            end_day = date(self.year, month_num, monthrange(self.year, month_num)[1])
            amount = self._compute_expense_by_region(start_day, end_day, region, move_type, with_vat=with_vat)
            vat = 0.0
            if with_vat:
                vat = self._compute_vat_by_region_expense(start_day, end_day, region, move_type)
            return amount, vat

        sheet.write(row_num, 0, 'Expenses', section_header_format)
        sheet.merge_range(row_num, 1, row_num, len(months)*2, '', section_header_format)
        row_num += 1

        expense_section_totals_amount = {m: 0.0 for m in months}
        expense_section_totals_vat = {m: 0.0 for m in months}

        # Combined Expense from Oman (with + 0% VAT)
        sheet.write(row_num, 0, 'Expense from Oman', label_format)
        current_col = 1
        for m_str in months:
            m_int = int(m_str)
            amount_vat, vat1 = get_data_for_excel(m_int, 'Oman', 'in_invoice', with_vat=True)
            amount_no_vat, _ = get_data_for_excel(m_int, 'Oman', 'in_invoice', with_vat=False)
            total_amount = amount_vat + amount_no_vat
            sheet.write(row_num, current_col, total_amount, data_format)
            sheet.write(row_num, current_col + 1, vat1, data_format)
            expense_section_totals_amount[m_str] += total_amount
            expense_section_totals_vat[m_str] += vat1
            current_col += 2
        row_num += 1

        # UAE
        sheet.write(row_num, 0, 'Expense from United Arab Emirates', label_format)
        current_col = 1
        for m_str in months:
            m_int = int(m_str)
            amount, vat = get_data_for_excel(m_int, 'United Arab Emirates', 'in_invoice', with_vat=True)
            sheet.write(row_num, current_col, amount, data_format)
            sheet.write(row_num, current_col + 1, vat, data_format)
            expense_section_totals_amount[m_str] += amount
            expense_section_totals_vat[m_str] += vat
            current_col += 2
        row_num += 1

        # Other Countries
        sheet.write(row_num, 0, 'Expense from Other Countries', label_format)
        current_col = 1
        for m_str in months:
            m_int = int(m_str)
            amount, vat = get_data_for_excel(m_int, 'Other', 'in_invoice', with_vat=True)
            sheet.write(row_num, current_col, amount, data_format)
            sheet.write(row_num, current_col + 1, vat, data_format)
            expense_section_totals_amount[m_str] += amount
            expense_section_totals_vat[m_str] += vat
            current_col += 2
        row_num += 1

        sheet.write(row_num, 0, 'Total Expenses', total_row_format)
        current_col = 1
        for m_str in months:
            sheet.write(row_num, current_col, expense_section_totals_amount[m_str], total_row_format)
            sheet.write(row_num, current_col + 1, expense_section_totals_vat[m_str], total_row_format)
            current_col += 2
        row_num += 2

        sheet.write(row_num, 0, 'Expense Returns', section_header_format)
        sheet.merge_range(row_num, 1, row_num, len(months)*2, '', section_header_format)
        row_num += 1

        returns_section_totals_amount = {m: 0.0 for m in months}
        returns_section_totals_vat = {m: 0.0 for m in months}

        # Combined Expense Return from Oman (with + 0% VAT)
        sheet.write(row_num, 0, 'Expense Return from Oman', label_format)
        current_col = 1
        for m_str in months:
            m_int = int(m_str)
            amount_vat, vat1 = get_data_for_excel(m_int, 'Oman', 'in_refund', with_vat=True)
            amount_no_vat, _ = get_data_for_excel(m_int, 'Oman', 'in_refund', with_vat=False)
            total_amount = amount_vat + amount_no_vat
            sheet.write(row_num, current_col, total_amount, data_format)
            sheet.write(row_num, current_col + 1, vat1, data_format)
            returns_section_totals_amount[m_str] += total_amount
            returns_section_totals_vat[m_str] += vat1
            current_col += 2
        row_num += 1

        # Expense Return from UAE
        sheet.write(row_num, 0, 'Expense Return from United Arab Emirates', label_format)
        current_col = 1
        for m_str in months:
            m_int = int(m_str)
            amount, vat = get_data_for_excel(m_int, 'United Arab Emirates', 'in_refund', with_vat=True)
            sheet.write(row_num, current_col, amount, data_format)
            sheet.write(row_num, current_col + 1, vat, data_format)
            returns_section_totals_amount[m_str] += amount
            returns_section_totals_vat[m_str] += vat
            current_col += 2
        row_num += 1

        # Expense Return from Other
        sheet.write(row_num, 0, 'Expense Return from Other Countries', label_format)
        current_col = 1
        for m_str in months:
            m_int = int(m_str)
            amount, vat = get_data_for_excel(m_int, 'Other', 'in_refund', with_vat=True)
            sheet.write(row_num, current_col, amount, data_format)
            sheet.write(row_num, current_col + 1, vat, data_format)
            returns_section_totals_amount[m_str] += amount
            returns_section_totals_vat[m_str] += vat
            current_col += 2
        row_num += 1

        sheet.write(row_num, 0, 'Total Expense Returns', total_row_format)
        current_col = 1
        for m_str in months:
            sheet.write(row_num, current_col, returns_section_totals_amount[m_str], total_row_format)
            sheet.write(row_num, current_col + 1, returns_section_totals_vat[m_str], total_row_format)
            current_col += 2
        row_num += 2

        sheet.write(row_num, 0, 'Net Total Expense', net_total_row_format)
        current_col = 1
        for m_str in months:
            net_amount = expense_section_totals_amount[m_str] - returns_section_totals_amount[m_str]
            net_vat = expense_section_totals_vat[m_str] - returns_section_totals_vat[m_str]
            sheet.write(row_num, current_col, net_amount, net_total_row_format)
            sheet.write(row_num, current_col + 1, net_vat, net_total_row_format)
            current_col += 2
        row_num += 1

        sheet.set_column(0, 0, 45)
        for i in range(1, len(months) * 2 + 1):
            sheet.set_column(i, i, 15)


    def _export_sales_and_returns_to_sheet(self, sheet, workbook):
        header_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1, 'bg_color': '#D3D3D3'})
        subheader_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
        data_format = workbook.add_format({'num_format': '#,##0.000', 'align': 'right', 'border': 1})
        title_format = workbook.add_format({'bold': True, 'font_size': 14})
        detail_header_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1, 'bg_color': '#ADD8E6'})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd', 'align': 'left', 'border': 1})
        text_format = workbook.add_format({'align': 'left', 'border': 1})

        months = [line.month for line in self.monthly_line_ids]
        month_names = dict(self.env['vat.report.monthly.line']._fields['month'].selection)

        row = 0
        sheet.write(row, 0, 'Sales Summary', title_format)
        row += 2
        sheet.write(row, 0, '', header_format)
        col = 1
        for m in months:
            sheet.merge_range(row, col, row, col+1, month_names.get(m, m), header_format)
            col += 2

        row += 1
        sheet.write(row, 0, '', subheader_format)
        col = 1
        for _ in months:
            sheet.write(row, col, 'Amount', subheader_format)
            sheet.write(row, col + 1, 'VAT', subheader_format)
            col += 2

        row += 1
        sheet.write(row, 0, 'Sales with VAT')
        col = 1
        for m in months:
            line = self.monthly_line_ids.filtered(lambda l: l.month == m)
            sheet.write(row, col, line.sales_with_vat if line else 0.0, data_format)
            sheet.write(row, col + 1, line.sales_vat_output if line else 0.0, data_format)
            col += 2

        row += 1
        sheet.write(row, 0, 'Sales 0% VAT')
        col = 1
        for m in months:
            line = self.monthly_line_ids.filtered(lambda l: l.month == m)
            sheet.write(row, col, line.sales_without_vat if line else 0.0, data_format)
            sheet.write(row, col + 1, 0.0, data_format)
            col += 2

        row += 2
        sheet.write(row, 0, 'Detailed Sales Transactions', detail_header_format)
        row += 1
        headers = ['Date', 'Invoice', 'Partner', 'Country', 'Product', 'Amount', 'VAT']
        for i, h in enumerate(headers):
            sheet.write(row, i, h, subheader_format)

        sales_moves = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('company_id', '=', self.company_id.id)
        ])

        row += 1
        for move in sales_moves:
            for line in move.invoice_line_ids:
                vat = sum((t.amount / 100) * line.price_subtotal for t in line.tax_ids if t.amount_type == 'percent')
                sheet.write(row, 0, move.invoice_date, date_format)
                sheet.write(row, 1, move.name, text_format)
                sheet.write(row, 2, move.partner_id.display_name, text_format)
                sheet.write(row, 3, move.partner_id.country_id.name or '', text_format)
                sheet.write(row, 4, line.name or line.product_id.name, text_format)
                sheet.write(row, 5, line.price_subtotal, data_format)
                sheet.write(row, 6, vat, data_format)
                row += 1

        row += 2
        sheet.write(row, 0, 'Sales Return Summary', title_format)
        row += 2
        sheet.write(row, 0, '', header_format)
        col = 1
        for m in months:
            sheet.merge_range(row, col, row, col+1, month_names.get(m, m), header_format)
            col += 2

        row += 1
        sheet.write(row, 0, '', subheader_format)
        col = 1
        for _ in months:
            sheet.write(row, col, 'Amount', subheader_format)
            sheet.write(row, col + 1, 'VAT', subheader_format)
            col += 2

        row += 1
        sheet.write(row, 0, 'Return with VAT')
        col = 1
        for m in months:
            line = self.credit_line_ids.filtered(lambda l: l.month == m)
            sheet.write(row, col, line.credit_with_vat if line else 0.0, data_format)
            sheet.write(row, col + 1, line.credit_vat_output if line else 0.0, data_format)
            col += 2

        row += 1
        sheet.write(row, 0, 'Return 0% VAT')
        col = 1
        for m in months:
            line = self.credit_line_ids.filtered(lambda l: l.month == m)
            sheet.write(row, col, line.credit_without_vat if line else 0.0, data_format)
            sheet.write(row, col + 1, 0.0, data_format)
            col += 2

        row += 2
        sheet.write(row, 0, 'Detailed Sales Return Transactions', detail_header_format)
        row += 1
        for i, h in enumerate(headers):
            sheet.write(row, i, h, subheader_format)

        returns = self.env['account.move'].search([
            ('move_type', '=', 'out_refund'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('company_id', '=', self.company_id.id)
        ])

        row += 1
        for move in returns:
            for line in move.invoice_line_ids:
                vat = sum((t.amount / 100) * line.price_subtotal for t in line.tax_ids if t.amount_type == 'percent')
                sheet.write(row, 0, move.invoice_date, date_format)
                sheet.write(row, 1, move.name, text_format)
                sheet.write(row, 2, move.partner_id.display_name, text_format)
                sheet.write(row, 3, move.partner_id.country_id.name or '', text_format)
                sheet.write(row, 4, line.name or line.product_id.name, text_format)
                sheet.write(row, 5, abs(line.price_subtotal), data_format)
                sheet.write(row, 6, abs(vat), data_format)
                row += 1

        sheet.set_column(0, 0, 15)
        sheet.set_column(1, 1, 20)
        sheet.set_column(2, 2, 25)
        sheet.set_column(3, 3, 20)
        sheet.set_column(4, 4, 35)
        sheet.set_column(5, 6, 15)

    def _export_combined_purchase_data(self, sheet, workbook, move_type):
        from calendar import monthrange
        from datetime import date

        header_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#D3D3D3'})
        subheader_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
        data_format = workbook.add_format({'num_format': '#,##0.000', 'align': 'right', 'border': 1})
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'left'})
        label_format = workbook.add_format({'bold': True, 'align': 'left', 'border': 1})
        detailed_section_header_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1, 'bg_color': '#ADD8E6'})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd', 'align': 'left', 'border': 1})
        text_format = workbook.add_format({'align': 'left', 'border': 1})

        regions = ['Oman', 'United Arab Emirates', 'Other']
        row_num = 0
        months = list(dict.fromkeys(line.month for line in self.monthly_line_ids))
        month_names = dict(self.env['vat.report.monthly.line']._fields['month'].selection)

        report_title = "Purchase Report" if move_type == 'in_invoice' else "Purchase Return Report"
        sheet.merge_range(row_num, 0, row_num, 3, f'{report_title} - Year: {self.year} Q{self.quarter_name}', title_format)
        row_num += 2

        expense_option_lines = self.env['account.expense.option.line'].search([('company_id', '=', self.company_id.id)])
        expense_account_data = {}
        for exp_line in expense_option_lines:
            account_name = exp_line.account_id.name
            option = exp_line.option_selection
            expense_account_data[exp_line.id] = {
                'account': account_name,
                'account_id': exp_line.account_id.id,
                'option': option,
                'monthly': {m: {r: {'amount': 0.0, 'vat': 0.0} for r in regions} for m in months}
            }
            for m_str in months:
                m_int = int(m_str)
                start_day = date(self.year, m_int, 1)
                end_day = date(self.year, m_int, monthrange(self.year, m_int)[1])

                moves = self.env['account.move'].search([
                    ('move_type', '=', move_type), ('state', '=', 'posted'),
                    ('invoice_date', '>=', start_day), ('invoice_date', '<=', end_day),
                    ('line_ids.account_id', '=', exp_line.account_id.id),
                    ('company_id', '=', self.company_id.id)
                ])

                for move in moves:
                    region = move.partner_id.country_id.name if move.partner_id.country_id.name in regions else 'Other'
                    amount = sum(abs(l.debit - l.credit) for l in move.line_ids if l.account_id == exp_line.account_id)
                    vat_amount = sum(abs(l.balance) for l in move.line_ids if l.tax_line_id)
                    expense_account_data[exp_line.id]['monthly'][m_str][region]['amount'] += amount
                    expense_account_data[exp_line.id]['monthly'][m_str][region]['vat'] += vat_amount

        # ---------------- Summary Section --------------------
        sheet.write(row_num, 0, '', header_format)
        col = 1
        for m in months:
            sheet.merge_range(row_num, col, row_num, col + 1, month_names.get(m, m), header_format)
            col += 2
        row_num += 1
        sheet.write(row_num, 0, '', subheader_format)
        col = 1
        for _ in months:
            sheet.write(row_num, col, 'Amount', subheader_format)
            sheet.write(row_num, col + 1, 'VAT', subheader_format)
            col += 2
        row_num += 1

        for region in regions:
            sheet.write(row_num, 0, f'{report_title} from {region}', label_format)
            current_col = 1
            for m_str in months:
                m_int = int(m_str)
                start_day = date(self.year, m_int, 1)
                end_day = date(self.year, m_int, monthrange(self.year, m_int)[1])

                amount_with_vat = self._compute_purchase_by_region(start_day, end_day, region, move_type, with_vat=True)
                vat_amount = self._compute_vat_by_region(start_day, end_day, region, move_type)
                amount_without_vat = self._compute_purchase_by_region(start_day, end_day, region, move_type, with_vat=False)

                expense_amount = sum(
                    d['monthly'][m_str][region]['amount'] for d in expense_account_data.values() if d['option'] == 'include_expense'
                )
                expense_vat = sum(
                    d['monthly'][m_str][region]['vat'] for d in expense_account_data.values() if d['option'] == 'include_expense'
                )

                total_amount = amount_with_vat + amount_without_vat + expense_amount if region == 'Oman' else amount_with_vat + expense_amount
                total_vat = vat_amount + expense_vat

                sheet.write(row_num, current_col, total_amount, data_format)
                sheet.write(row_num, current_col + 1, total_vat, data_format)
                current_col += 2
            row_num += 1

            # Separate line for show_separate_line
            if region == 'Oman':
                for exp_data in expense_account_data.values():
                    if exp_data['option'] == 'show_expense_row':
                        sheet.write(row_num, 0, f"{exp_data['account']} (Expense)", label_format)
                        current_col = 1
                        for m_str in months:
                            total_amt = sum(exp_data['monthly'][m_str][r]['amount'] for r in regions)
                            total_vat = sum(exp_data['monthly'][m_str][r]['vat'] for r in regions)
                            sheet.write(row_num, current_col, total_amt, data_format)
                            sheet.write(row_num, current_col + 1, total_vat, data_format)
                            current_col += 2
                        row_num += 1

        row_num += 2  # Space before detailed section

        # ----------------- Detailed Section -----------------
        for region in regions:
            detailed_title = f'Detailed {"Purchase" if move_type == "in_invoice" else "Purchase Return"} - {region}'
            sheet.write(row_num, 0, detailed_title, detailed_section_header_format)
            sheet.merge_range(row_num, 1, row_num, 6, '', detailed_section_header_format)
            row_num += 1

            headers = ['Date', 'Invoice/Refund', 'Partner', 'Partner Country', 'Product/Account', 'Amount', 'VAT']
            for col, head in enumerate(headers):
                sheet.write(row_num, col, head, subheader_format)
            row_num += 1

            domain = [
                ('move_type', '=', move_type),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', self.start_date),
                ('invoice_date', '<=', self.end_date),
                ('company_id', '=', self.company_id.id),
            ]
            if region == 'Other':
                domain.append(('partner_id.country_id.name', 'not in', ['Oman', 'United Arab Emirates']))
            else:
                domain.append(('partner_id.country_id.name', '=', region))

            moves = self.env['account.move'].search(domain, order='date asc')

            for move in moves:
                for line in move.invoice_line_ids.filtered(lambda l: l.account_id.account_type == 'expense_direct_cost'):
                    amount = abs(line.price_subtotal)
                    vat = sum(abs((tax.amount / 100.0) * line.price_subtotal) for tax in line.tax_ids if tax.amount_type == 'percent')

                    sheet.write(row_num, 0, move.invoice_date, date_format)
                    sheet.write(row_num, 1, move.name, text_format)
                    sheet.write(row_num, 2, move.partner_id.display_name, text_format)
                    sheet.write(row_num, 3, move.partner_id.country_id.name or '', text_format)
                    sheet.write(row_num, 4, line.name or line.product_id.display_name or line.account_id.display_name, text_format)
                    sheet.write(row_num, 5, amount, data_format)
                    sheet.write(row_num, 6, vat, data_format)
                    row_num += 1
            row_num += 3

        # ---------------- Detailed Expense Section for include_expense ----------------
        for exp_data in expense_account_data.values():
            if exp_data['option'] == 'include_expense':
                sheet.write(row_num, 0, f'Detailed Expenses - {exp_data["account"]}', detailed_section_header_format)
                sheet.merge_range(row_num, 1, row_num, 6, '', detailed_section_header_format)
                row_num += 1

                headers = ['Date', 'Invoice/Refund', 'Partner', 'Partner Country', 'Product/Account', 'Amount', 'VAT']
                for col, head in enumerate(headers):
                    sheet.write(row_num, col, head, subheader_format)
                row_num += 1

                expense_moves = self.env['account.move'].search([
                    ('move_type', '=', move_type), ('state', '=', 'posted'),
                    ('invoice_date', '>=', self.start_date), ('invoice_date', '<=', self.end_date),
                    ('line_ids.account_id', '=', exp_data['account_id']),
                    ('company_id', '=', self.company_id.id),
                ])

                for move in expense_moves:
                    for line in move.line_ids.filtered(lambda l: l.account_id.id == exp_data['account_id']):
                        amount = abs(line.debit - line.credit)
                        vat = sum(abs(tax_line.debit - tax_line.credit) for tax_line in move.line_ids.filtered(lambda t: t.tax_line_id))

                        sheet.write(row_num, 0, move.invoice_date, date_format)
                        sheet.write(row_num, 1, move.name, text_format)
                        sheet.write(row_num, 2, move.partner_id.display_name, text_format)
                        sheet.write(row_num, 3, move.partner_id.country_id.name or '', text_format)
                        sheet.write(row_num, 4, exp_data['account'], text_format)
                        sheet.write(row_num, 5, amount, data_format)
                        sheet.write(row_num, 6, vat, data_format)
                        row_num += 1
                row_num += 3
        # ---------------- Detailed Expense Section for show_separate_line ----------------
        for exp_data in expense_account_data.values():
            if exp_data['option'] == 'show_expense_row':
                sheet.write(row_num, 0, f'Detailed Expenses - {exp_data["account"]}', detailed_section_header_format)
                sheet.merge_range(row_num, 1, row_num, 6, '', detailed_section_header_format)
                row_num += 1

                headers = ['Date', 'Invoice/Refund', 'Partner', 'Partner Country', 'Product/Account', 'Amount', 'VAT']
                for col, head in enumerate(headers):
                    sheet.write(row_num, col, head, subheader_format)
                row_num += 1

                expense_moves = self.env['account.move'].search([
                    ('move_type', '=', move_type), ('state', '=', 'posted'),
                    ('invoice_date', '>=', self.start_date), ('invoice_date', '<=', self.end_date),
                    ('line_ids.account_id', '=', exp_data['account_id']),
                    ('company_id', '=', self.company_id.id),
                ])

                for move in expense_moves:
                    for line in move.line_ids.filtered(lambda l: l.account_id.id == exp_data['account_id']):
                        amount = abs(line.debit - line.credit)
                        vat = sum(abs(tax_line.debit - tax_line.credit) for tax_line in move.line_ids.filtered(lambda t: t.tax_line_id))

                        sheet.write(row_num, 0, move.invoice_date, date_format)
                        sheet.write(row_num, 1, move.name, text_format)
                        sheet.write(row_num, 2, move.partner_id.display_name, text_format)
                        sheet.write(row_num, 3, move.partner_id.country_id.name or '', text_format)
                        sheet.write(row_num, 4, exp_data['account'], text_format)
                        sheet.write(row_num, 5, amount, data_format)
                        sheet.write(row_num, 6, vat, data_format)
                        row_num += 1
                row_num += 3


        # Final column widths
        sheet.set_column(0, 0, 15)
        sheet.set_column(1, 1, 20)
        sheet.set_column(2, 2, 25)
        sheet.set_column(3, 3, 20)
        sheet.set_column(4, 4, 35)
        sheet.set_column(5, 6, 15)

    def _export_combined_expense_data(self, sheet, workbook, move_type):
        header_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'bg_color': '#D3D3D3'})
        subheader_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
        data_format = workbook.add_format({'num_format': '#,##0.000', 'align': 'right', 'border': 1})
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'left'})
        label_format = workbook.add_format({'bold': True, 'align': 'left', 'border': 1})
        detailed_section_header_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1, 'bg_color': '#ADD8E6'})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd', 'align': 'left', 'border': 1})
        text_format = workbook.add_format({'align': 'left', 'border': 1})

        regions = ['Oman', 'United Arab Emirates', 'Other']
        row_num = 0
        months = list(dict.fromkeys(line.month for line in self.monthly_line_ids))
        month_names = dict(self.env['vat.report.monthly.line']._fields['month'].selection)

        report_title = "Expense Report" if move_type == 'in_invoice' else "Expense Return Report"
        sheet.merge_range(row_num, 0, row_num, 3, f'{report_title} - Year: {self.year} Q{self.quarter_name}', title_format)
        row_num += 2

        # --- Summary Section ---
        for region in regions:
            sheet.write(row_num, 0, f'{report_title} from {region}', label_format)
            current_col = 1
            for m in months:
                start_date, end_date = self._get_month_date_range(m)
                amount_with_vat = self._compute_expense_by_region(start_date, end_date, region, move_type, with_vat=True)
                vat_amount = self._compute_vat_by_region_expense(start_date, end_date, region, move_type)
                amount_without_vat = self._compute_expense_by_region(start_date, end_date, region, move_type, with_vat=False)
                total_amount = amount_with_vat + amount_without_vat if region == 'Oman' else amount_with_vat
                sheet.write(row_num, current_col, total_amount, data_format)
                sheet.write(row_num, current_col + 1, vat_amount, data_format)
                current_col += 2
            row_num += 1

        row_num += 1
        sheet.write(row_num, 0, '', header_format)
        col = 1
        for m in months:
            sheet.merge_range(row_num, col, row_num, col + 1, month_names.get(m, m), header_format)
            col += 2
        row_num += 1
        sheet.write(row_num, 0, '', subheader_format)
        col = 1
        for _ in months:
            sheet.write(row_num, col, 'Amount', subheader_format)
            sheet.write(row_num, col + 1, 'VAT', subheader_format)
            col += 2
        row_num += 2

        # --- Detailed Transactions ---
        for region in regions:
            detailed_title = f'Detailed {"Expense" if move_type == "in_invoice" else "Expense Return"} - {region}'
            sheet.write(row_num, 0, detailed_title, detailed_section_header_format)
            sheet.merge_range(row_num, 1, row_num, 6, '', detailed_section_header_format)
            row_num += 1

            headers = ['Date', 'Invoice/Refund', 'Partner', 'Partner Country', 'Account', 'Amount', 'VAT']
            for col, head in enumerate(headers):
                sheet.write(row_num, col, head, subheader_format)
            row_num += 1

            domain = [
                ('move_type', '=', move_type),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', self.start_date),
                ('invoice_date', '<=', self.end_date),
                ('company_id', '=', self.company_id.id),
            ]
            if region == 'Other':
                domain.append(('partner_id.country_id.name', 'not in', ['Oman', 'United Arab Emirates']))
            else:
                domain.append(('partner_id.country_id.name', '=', region))

            moves = self.env['account.move'].search(domain, order='date asc')

            for move in moves:
                for line in move.line_ids.filtered(lambda l: l.account_id.account_type == 'expense' and not l.tax_line_id):
                    amount = abs(line.balance)
                    vat = sum(abs(tax_line.debit - tax_line.credit) for tax_line in move.line_ids.filtered(lambda t: t.tax_line_id))

                    sheet.write(row_num, 0, move.invoice_date, date_format)
                    sheet.write(row_num, 1, move.name, text_format)
                    sheet.write(row_num, 2, move.partner_id.display_name, text_format)
                    sheet.write(row_num, 3, move.partner_id.country_id.name or '', text_format)
                    sheet.write(row_num, 4, line.account_id.name or '', text_format)
                    sheet.write(row_num, 5, amount, data_format)
                    sheet.write(row_num, 6, vat, data_format)
                    row_num += 1

            row_num += 3

        # Adjust column widths
        sheet.set_column(0, 0, 15)
        sheet.set_column(1, 1, 20)
        sheet.set_column(2, 2, 25)
        sheet.set_column(3, 3, 20)
        sheet.set_column(4, 4, 35)
        sheet.set_column(5, 6, 15)

  
    
    def _render_expense_details_table(self):
        from collections import defaultdict

        for rec in self:
            months = [int(line.month) for line in rec.monthly_line_ids]
            month_names = dict(self.env['vat.report.monthly.line']._fields['month'].selection)

            if not months:
                rec.expense_details_table_html = ''
                continue

            # Fetch all posted expense move lines
            all_lines = self.env['account.move.line'].search([
                ('invoice_date', '>=', rec.start_date),
                ('invoice_date', '<=', rec.end_date),
                ('company_id', '=', rec.company_id.id),
                ('move_id.state', '=', 'posted'),
                ('move_id.move_type', 'in', ['in_invoice'])
            ])

            # Data structures
            account_data = defaultdict(lambda: defaultdict(lambda: {'amount': 0.0, 'vat': 0.0}))

            for line in all_lines:
                if line.account_id.account_type != 'expense':
                    continue

                account_key = f"{line.account_id.code} {line.account_id.name}"
                m = line.invoice_date.month
                if m not in months:
                    continue

                account_data[account_key][m]['amount'] += line.balance

            # Now compute VAT lines linked to expenses
            tax_lines = all_lines.filtered(lambda l: l.tax_line_id)

            for line in tax_lines:
                m = line.invoice_date.month
                if m not in months:
                    continue

                # Check if this tax line belongs to a move that has an expense line
                expense_lines = line.move_id.line_ids.filtered(lambda l: l.account_id.account_type == 'expense')
                if not expense_lines:
                    continue

                for expense_line in expense_lines:
                    account_key = f"{expense_line.account_id.code} {expense_line.account_id.name}"
                    vat_val = line.debit - line.credit
                    account_data[account_key][m]['vat'] += vat_val

            # Build table headers
            header_month_cells = ''.join(
                f"<th colspan='2' style='text-align:center;'>{month_names[str(m)]}</th>" for m in months
            )
            sub_headers = ''.join(
                "<th style='text-align:right;'>Amt</th><th style='text-align:right;'>VAT</th>" for _ in months
            )

            table_html = f"""
                <table class="table table-sm table-bordered o_list_table" style="width: 100%;">
                    <thead>
                        <tr><th>Expense Account</th>{header_month_cells}</tr>
                        <tr><th></th>{sub_headers}</tr>
                    </thead>
                    <tbody>
            """

            def fmt(val):
                return f"{val:,.3f}" if val else "0.000"

            # Data rows
            for account, values in sorted(account_data.items()):
                row = f"<tr><td>{account}</td>"
                for m in months:
                    row += f"<td style='text-align:right;'>{fmt(values[m]['amount'])}</td>"
                    row += f"<td style='text-align:right;'>{fmt(values[m]['vat'])}</td>"
                row += "</tr>"
                table_html += row

            # Total row at the bottom
            total_row = "<tr><td><strong>Total</strong></td>"
            for m in months:
                total_amt = sum(acc[m]['amount'] for acc in account_data.values())
                total_vat = sum(acc[m]['vat'] for acc in account_data.values())
                total_row += f"<td style='text-align:right; font-weight:bold;'>{fmt(total_amt)}</td>"
                total_row += f"<td style='text-align:right; font-weight:bold;'>{fmt(total_vat)}</td>"
            total_row += "</tr>"
            table_html += total_row

            table_html += "</tbody></table>"
            rec.expense_details_table_html = table_html



    def _export_expense_account_names_sheet(self, sheet, workbook):
        import datetime
        from collections import defaultdict

        # Formats
        header_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1, 'bg_color': '#D3D3D3'})
        subheader_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
        data_format = workbook.add_format({'num_format': '#,##0.000', 'align': 'right', 'border': 1})
        title_format = workbook.add_format({'bold': True, 'font_size': 14})

        # Get months
        quarter_months = {
            '1': [1, 2, 3],
            '2': [4, 5, 6],
            '3': [7, 8, 9],
            '4': [10, 11, 12],
        }
        months = quarter_months.get(self.quarter_name, [])
        month_names = [datetime.date(1900, m, 1).strftime('%B') for m in months]

        # Title
        sheet.write('A1', f'Expense Account Summary - Q{self.quarter_name} {self.year}', title_format)

        # Header
        row = 2
        sheet.write(row, 0, '', header_format)
        col = 1
        for month in month_names:
            sheet.merge_range(row, col, row, col + 1, month, header_format)
            col += 2
        sheet.write(row, col, '', header_format)  # Empty for alignment

        # Subheaders
        row += 1
        sheet.write(row, 0, 'Expense Account', subheader_format)
        col = 1
        for _ in months:
            sheet.write(row, col, 'Amount', subheader_format)
            sheet.write(row, col + 1, 'VAT', subheader_format)
            col += 2

        # Data structures
        account_data = defaultdict(lambda: defaultdict(lambda: {'amount': 0.0, 'vat': 0.0}))

        # Fetch expense lines
        domain = [
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date),
            ('company_id', '=', self.company_id.id),
            ('move_id.state', '=', 'posted'),
            ('move_id.move_type', '=', 'in_invoice'),  # only expense invoices, no returns
        ]
        lines = self.env['account.move.line'].search(domain)

        for line in lines:
            if line.account_id.account_type != 'expense':
                continue
            month = line.invoice_date.month
            if month not in months:
                continue
            account_key = f"{line.account_id.code} {line.account_id.name}"
            account_data[account_key][month]['amount'] += line.balance

        # Get tax lines linked to expense invoices
        tax_lines = lines.filtered(lambda l: l.tax_line_id)

        for line in tax_lines:
            month = line.invoice_date.month
            if month not in months:
                continue
            expense_lines = line.move_id.line_ids.filtered(lambda l: l.account_id.account_type == 'expense')
            if not expense_lines:
                continue
            vat_val = line.debit - line.credit
            for expense_line in expense_lines:
                acc_key = f"{expense_line.account_id.code} {expense_line.account_id.name}"
                account_data[acc_key][month]['vat'] += vat_val

        # Write data rows
        row += 1
        for acc_name, monthly_data in sorted(account_data.items()):
            sheet.write(row, 0, acc_name)
            col = 1
            for m in months:
                amt = monthly_data[m]['amount']
                vat = monthly_data[m]['vat']
                sheet.write(row, col, amt, data_format)
                sheet.write(row, col + 1, vat, data_format)
                col += 2
            row += 1

        # Total Row
        sheet.write(row, 0, 'Total', header_format)
        col = 1
        for m in months:
            total_amt = sum(acc[m]['amount'] for acc in account_data.values())
            total_vat = sum(acc[m]['vat'] for acc in account_data.values())
            sheet.write(row, col, total_amt, data_format)
            sheet.write(row, col + 1, total_vat, data_format)
            col += 2

        # Column Widths
        sheet.set_column(0, 0, 50)
        for c in range(1, col + 1):
            sheet.set_column(c, c, 15)

    def _get_month_date_range(self, month):
        """
        Returns the first and last date of the given month in the report's year.
        """
        from calendar import monthrange
        import datetime

        year = int(self.year)
        month = int(month)
        first_day = datetime.date(year, month, 1)
        last_day = datetime.date(year, month, monthrange(year, month)[1])
        return first_day, last_day

