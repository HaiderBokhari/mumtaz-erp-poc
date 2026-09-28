from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from accounting.models import ChartOfAccount, JournalEntry


class Employee(models.Model):
    """
    Requirement doc, HR #1: "Create, view, edit and terminate an employee
    having fields including Full Name, CNIC, Address, role, monthly salary,
    commission." Questionnaire #26: roughly 70 employees across branches.
    """

    STATUS_ACTIVE = 'ACTIVE'
    STATUS_TERMINATED = 'TERMINATED'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_TERMINATED, 'Terminated'),
    ]

    employee_number = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=150)
    cnic = models.CharField(max_length=20, unique=True, help_text='Pakistani CNIC, e.g. 38403-1234567-1')
    address = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=100, help_text='e.g. Distribution Representative, FSO, Warehouse Staff')
    warehouse = models.ForeignKey(
        'warehouses.Warehouse', null=True, blank=True, on_delete=models.SET_NULL, related_name='employees'
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='employee_record', help_text='Linked login account, if this employee has system access.',
    )
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_rate = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text='Default commission, either a flat monthly amount or a % of sales depending on role.',
    )
    hire_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    termination_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return f'{self.employee_number} - {self.full_name}'

    def terminate(self, on_date=None):
        self.status = self.STATUS_TERMINATED
        self.termination_date = on_date or timezone.localdate()
        self.save(update_fields=['status', 'termination_date', 'updated_at'])


class SalaryPayment(models.Model):
    """
    Requirement doc, HR #2: "Record monthly salaries paid to staff. The
    fields will be limited to month, year, salary paid, commission amount."
    """

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_payments')
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    salary_paid = models.DecimalField(max_digits=12, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_on = models.DateField(default=timezone.localdate)

    class Meta:
        unique_together = ['employee', 'year', 'month']
        ordering = ['-year', '-month']

    def __str__(self):
        return f'{self.employee.employee_number} {self.month}-{self.year}'

    @property
    def total_paid(self):
        return self.salary_paid + self.commission_amount

    @transaction.atomic
    def post_to_ledger(self, user=None):
        """Dr Salary Expense, Cr Cash (requirement doc, Accounts #3: embedded, not a manual voucher)."""
        if self.total_paid <= 0:
            return
        JournalEntry.create_posted(
            source=JournalEntry.SOURCE_VOUCHER,
            lines=[
                {'account': ChartOfAccount.SALARY_EXPENSE, 'debit': self.total_paid},
                {'account': ChartOfAccount.CASH, 'credit': self.total_paid},
            ],
            date=self.paid_on,
            narration=f'Salary {self.month}/{self.year}: {self.employee.full_name}',
            reference=self.employee.employee_number, created_by=user,
        )


class LeaveRequest(models.Model):
    """Leave management — questionnaire #25: "Leave management must be included"."""

    TYPE_CASUAL = 'CASUAL'
    TYPE_SICK = 'SICK'
    TYPE_ANNUAL = 'ANNUAL'
    TYPE_UNPAID = 'UNPAID'
    TYPE_CHOICES = [
        (TYPE_CASUAL, 'Casual'),
        (TYPE_SICK, 'Sick'),
        (TYPE_ANNUAL, 'Annual'),
        (TYPE_UNPAID, 'Unpaid'),
    ]

    STATUS_PENDING = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f'{self.employee.full_name}: {self.leave_type} {self.start_date} - {self.end_date}'

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1

    def decide(self, approve, user):
        self.status = self.STATUS_APPROVED if approve else self.STATUS_REJECTED
        self.approved_by = user
        self.decided_at = timezone.now()
        self.save(update_fields=['status', 'approved_by', 'decided_at'])
