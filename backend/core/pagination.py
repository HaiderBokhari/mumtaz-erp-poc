from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """25 per page by default; ?page_size= lets list screens ask for more (capped)."""
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 500
