from rest_framework import serializers

from .models import Employee, LeaveRequest, SalaryPayment


class EmployeeSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = Employee
        fields = [
            'id', 'employee_number', 'full_name', 'cnic', 'address', 'role',
            'warehouse', 'warehouse_name', 'user', 'monthly_salary', 'commission_rate',
            'hire_date', 'status', 'termination_date', 'created_at', 'updated_at',
        ]


class SalaryPaymentSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    employee_number = serializers.CharField(source='employee.employee_number', read_only=True)
    total_paid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = SalaryPayment
        fields = [
            'id', 'employee', 'employee_name', 'employee_number', 'year', 'month',
            'salary_paid', 'commission_amount', 'total_paid', 'paid_on',
        ]


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    days = serializers.IntegerField(read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            'id', 'employee', 'employee_name', 'leave_type', 'start_date', 'end_date',
            'days', 'reason', 'status', 'approved_by', 'requested_at', 'decided_at',
        ]
        read_only_fields = ['status', 'approved_by', 'decided_at']
