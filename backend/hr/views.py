from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import RolePermission

from .models import Employee, LeaveRequest, SalaryPayment
from .serializers import EmployeeSerializer, LeaveRequestSerializer, SalaryPaymentSerializer


class EmployeeViewSet(viewsets.ModelViewSet):
    """Requirement doc, HR #1."""
    queryset = Employee.objects.select_related('warehouse', 'user').all()
    serializer_class = EmployeeSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['warehouse', 'status', 'role']
    search_fields = ['employee_number', 'full_name', 'cnic']

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        employee = self.get_object()
        employee.terminate()
        return Response(EmployeeSerializer(employee).data)


class SalaryPaymentViewSet(viewsets.ModelViewSet):
    """Requirement doc, HR #2, #3, #4 (payouts + payslip by employee number)."""
    queryset = SalaryPayment.objects.select_related('employee')
    serializer_class = SalaryPaymentSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['employee', 'year', 'month']

    @action(detail=False, methods=['get'])
    def slip(self, request):
        """Monthly salary slip by employee number (requirement doc, HR #4)."""
        employee_number = request.query_params.get('employee_number')
        year = request.query_params.get('year')
        month = request.query_params.get('month')
        payment = SalaryPayment.objects.filter(
            employee__employee_number=employee_number, year=year, month=month
        ).select_related('employee').first()
        if not payment:
            return Response({'detail': 'No salary payment found for that employee/month/year.'}, status=404)
        return Response(SalaryPaymentSerializer(payment).data)


class LeaveRequestViewSet(viewsets.ModelViewSet):
    """Leave management (questionnaire #25)."""
    queryset = LeaveRequest.objects.select_related('employee')
    serializer_class = LeaveRequestSerializer
    permission_classes = [RolePermission]
    filterset_fields = ['employee', 'status', 'leave_type']

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        leave = self.get_object()
        leave.decide(approve=True, user=request.user)
        return Response(LeaveRequestSerializer(leave).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        leave = self.get_object()
        leave.decide(approve=False, user=request.user)
        return Response(LeaveRequestSerializer(leave).data)
