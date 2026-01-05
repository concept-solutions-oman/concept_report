from odoo import http
from odoo.http import request
import io
import xlsxwriter
from datetime import datetime, time, date
import base64


class VatReportExcelExportController(http.Controller):
    _name = 'vat.report.excel.export.controller'

    @http.route('/vat_report/export_excel/<int:report_id>', type='http', auth='user')
    def export_vat_excel(self, report_id, **kwargs):
        report_record = request.env['vat.report'].with_context({'active_test': False}).sudo().browse(report_id)
        if not report_record.exists():
           
            return request.not_found()
        report_record.compute_all_values()
        report_record._compute_monthly_breakdown()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sales_sheet_combine = workbook.add_worksheet('Sales and Return')
        report_record._export_combined_sales_sheet(sales_sheet_combine, workbook)
        purchase_sheet_combine = workbook.add_worksheet('Purchase and Return')
        report_record._export_combined_purchase_sheet(purchase_sheet_combine, workbook)
        expense_acc_sheet = workbook.add_worksheet('Expense Accounts Name')
        report_record._export_expense_account_names_sheet(expense_acc_sheet, workbook)
        sales_sheet = workbook.add_worksheet('Sales & Returns')
        report_record._export_sales_and_returns_to_sheet(sales_sheet, workbook)
        purchase_sheet = workbook.add_worksheet('Purchase')
        report_record._export_combined_purchase_data(purchase_sheet, workbook, move_type='in_invoice')
        purchase_return_sheet = workbook.add_worksheet('Purchase Return')
        report_record._export_combined_purchase_data(purchase_return_sheet, workbook, move_type='in_refund')
        try:
            workbook.close()
        except Exception as e:
            
            return request.not_found(description=f"Error generating Excel: {e}")
        output.seek(0)
        base64_data = base64.b64encode(output.read()).decode('utf-8')
        file_name = f"VAT_Report_Q{report_record.quarter_name}_{report_record.year}.xlsx"
        file_url = f"data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{base64_data}"
        html = f"""
        <html>
            <body>
                <a id="download" href="{file_url}" download="{file_name}"></a>
                <script>
                    document.getElementById("download").click();
                    setTimeout(function() {{
                        window.location.href = "/web#action=cg_reports.action_vat_report&model=vat.report&view_type=form";
                    }}, 500);
                </script>
            </body>
        </html>
        """
        return request.make_response(html, [('Content-Type', 'text/html')])