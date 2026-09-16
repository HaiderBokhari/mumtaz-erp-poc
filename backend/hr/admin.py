from django.contrib import admin

from .models import Employee, LeaveRequest, SalaryPayment


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_number', 'full_name', 'role', 'warehouse', 'monthly_salary', 'status']
    list_filter = ['warehouse', 'status', 'role']
    search_fields = ['employee_number', 'full_name', 'cnic']


@admin.register(SalaryPayment)
class SalaryPaymentAdmin(admin.ModelAdmin):
    list_display = ['employee', 'year', 'month', 'salary_paid', 'commission_amount']
    list_filter = ['year', 'month']


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'start_date', 'end_date', 'status']
    list_filter = ['status', 'leave_type']
