export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface Me {
  id: number
  username: string
  first_name: string
  last_name: string
  email: string
  is_superuser: boolean
  roles: string[]
  profile: {
    phone: string
    dr_code: string
    warehouse: number | null
    supervisor: number | null
    is_blocked: boolean
  }
}

export interface Brand {
  id: number
  name: string
  code: string
  status: 'ACTIVE' | 'DISCONTINUED'
  sku_count: number
}

export interface SKU {
  id: number
  code: string
  name: string
  brand: number
  brand_name: string
  variant: string
  pack_size: string
  sticks_per_pack: number
  barcode: string
  current_cost_price: string
  status: 'ACTIVE' | 'DISCONTINUED'
}

export interface Channel {
  id: number
  name: string
  channel_type: 'DD' | 'VDD' | 'WS' | 'VWS' | 'MANDI'
  filer_status: 'FILER' | 'NON_FILER'
  status: 'ACTIVE' | 'DORMANT' | 'CLOSED'
  opened_on: string
  closed_on: string | null
}

export interface Warehouse {
  id: number
  name: string
  code: string
  location: string
  is_head_office: boolean
  requires_po_approval: boolean
  is_active: boolean
}

export interface StockLevel {
  id: number
  warehouse: number
  warehouse_name: string
  sku: number
  sku_code: string
  sku_name: string
  brand_name: string
  quantity: string
}

export interface PurchaseOrderLine {
  id?: number
  sku: number
  sku_code?: string
  sku_name?: string
  quantity: string
  unit_cost: string
  line_total?: string
}

export interface PurchaseOrder {
  id: number
  po_number: string
  ptc_reference_number: string
  warehouse: number
  warehouse_name: string
  supplier: number
  supplier_name: string
  status: 'DRAFT' | 'PENDING_APPROVAL' | 'SUBMITTED_TO_PTC' | 'RECEIVED' | 'CANCELLED'
  order_date: string
  notes: string
  total_value: string
  lines: PurchaseOrderLine[]
}

export interface Shop {
  id: number
  name: string
  channel: number
  channel_name: string
  address: string
  locality: string
  contact_name: string
  contact_phone: string
  credit_limit: string
  status: 'ACTIVE' | 'CLOSED'
  outstanding_balance: string
}

export interface SalesOrderLine {
  id?: number
  sku: number
  sku_code?: string
  sku_name?: string
  quantity: string
  unit_price: string
  line_total?: string
}

export interface SalesOrder {
  id: number
  so_number: string
  ptc_reference_number: string
  shop: number
  shop_name: string
  channel: number
  channel_name: string
  warehouse: number
  warehouse_name: string
  dr: number
  dr_name: string
  order_date: string
  timestamp: string
  status: 'DRAFT' | 'CONFIRMED' | 'CANCELLED'
  source: 'MANUAL' | 'BIZOM_UPLOAD'
  total_value: string
}

export interface DashboardData {
  stock_value: string
  todays_sales_value: string
  todays_sales_quantity: string
  mtd_sales_value: string
  open_purchase_orders: number
  low_stock_alerts: number
  outstanding_receivables: string
  collections_mtd: string
  sales_trend_30d: { day: string; value: string }[]
  channel_breakdown_mtd: { channel__name: string; value: string }[]
}
