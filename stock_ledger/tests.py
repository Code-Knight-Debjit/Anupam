import json
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from products.models import Brand, Category, Product
from .excel_import import import_opening_stock_workbook
from .models import Branch, BranchStock, OpeningStock, StockPurchase, StockSale, StockTransfer, UserProfile
from .services import recompute_branch_stock


def make_workbook_upload(rows, filename='upload.xlsx', extra_headers=None):
    """rows: list of [ID, Brand, Category, Branch, Quantity, Price, Location, *specs]."""
    wb = Workbook()
    ws = wb.active
    headers = ['ID', 'Brand', 'Category', 'Branch', 'Quantity', 'Price', 'Location']
    if extra_headers:
        headers += extra_headers
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return SimpleUploadedFile(filename, buf.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def make_user(username, role, branch=None, is_staff=True):
    user = User.objects.create_user(username=username, password='testpass123', is_staff=is_staff)
    UserProfile.objects.filter(user=user).delete()
    UserProfile.objects.create(user=user, role=role, branch=branch)
    return user


class StockLedgerTestBase(TestCase):
    def setUp(self):
        # Bengaluru/Chennai are seeded by the stock_ledger data migration.
        self.blr = Branch.objects.get(code='BLR')
        self.maa = Branch.objects.get(code='MAA')
        self.brand = Brand.objects.create(name='Timken', slug='timken')
        self.category = Category.objects.create(name='Bearings', slug='bearings')
        self.product = Product.objects.create(
            category=self.category, brand=self.brand, name='6001-ZZ', slug='6001-zz', sku='6001-ZZ',
        )
        self.admin = make_user('admin1', UserProfile.ADMIN)
        self.blr_staff = make_user('blrstaff', UserProfile.BRANCH_STAFF, branch=self.blr)
        self.maa_staff = make_user('maastaff', UserProfile.BRANCH_STAFF, branch=self.maa)
        self.viewer = make_user('viewer1', UserProfile.VIEWER)


class BranchScopingTests(StockLedgerTestBase):
    def test_branch_staff_cannot_edit_other_branch_opening_stock(self):
        entry = OpeningStock.objects.create(
            product=self.product, branch=self.maa, quantity=10, price=50, created_by=self.admin,
        )
        recompute_branch_stock(self.product.id, self.maa.id)

        self.client.force_login(self.blr_staff)
        url = reverse('dashboard:stock_ledger:opening_stock_edit', args=[entry.pk])
        response = self.client.post(url, {'quantity': 999, 'price': 1, 'effective_date': '2026-01-01'})
        self.assertEqual(response.status_code, 403)

        entry.refresh_from_db()
        self.assertEqual(entry.quantity, 10)

    def test_branch_staff_cannot_delete_other_branch_purchase(self):
        entry = StockPurchase.objects.create(
            product=self.product, branch=self.maa, quantity=5, price=20, created_by=self.admin,
        )
        self.client.force_login(self.blr_staff)
        url = reverse('dashboard:stock_ledger:purchase_delete', args=[entry.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        entry.refresh_from_db()
        self.assertFalse(entry.is_deleted)

    def test_branch_staff_cannot_reach_admin_only_dashboard_sections(self):
        self.client.force_login(self.blr_staff)
        for name in ['dashboard:home', 'dashboard:products', 'dashboard:categories', 'dashboard:brands']:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 403, f'{name} should 403 for Branch Staff')

    def test_branch_staff_cannot_reach_branch_or_user_management(self):
        self.client.force_login(self.blr_staff)
        response = self.client.get(reverse('dashboard:stock_ledger:branches'))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse('dashboard:stock_ledger:users'))
        self.assertEqual(response.status_code, 403)


class ViewerMutationTests(StockLedgerTestBase):
    def test_viewer_cannot_create_opening_stock(self):
        self.client.force_login(self.viewer)
        url = reverse('dashboard:stock_ledger:opening_stock_add')
        response = self.client.post(url, {
            'product': self.product.id, 'branch': self.blr.id, 'quantity': 5, 'price': 10,
            'effective_date': '2026-01-01',
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(OpeningStock.objects.count(), 0)

    def test_viewer_cannot_create_transfer(self):
        self.client.force_login(self.viewer)
        url = reverse('dashboard:stock_ledger:transfer_create')
        response = self.client.post(url, {
            'product': self.product.id, 'from_branch': self.blr.id, 'to_branch': self.maa.id, 'quantity': 5,
        })
        self.assertEqual(response.status_code, 403)

    def test_branch_staff_cannot_create_transfer(self):
        self.client.force_login(self.blr_staff)
        url = reverse('dashboard:stock_ledger:transfer_create')
        response = self.client.post(url, {
            'product': self.product.id, 'from_branch': self.blr.id, 'to_branch': self.maa.id, 'quantity': 5,
        })
        self.assertEqual(response.status_code, 403)


class TransferLifecycleTests(StockLedgerTestBase):
    def setUp(self):
        super().setUp()
        OpeningStock.objects.create(
            product=self.product, branch=self.blr, quantity=100, price=10, created_by=self.admin,
        )
        recompute_branch_stock(self.product.id, self.blr.id)

    def test_full_lifecycle_moves_stock_exactly_once(self):
        self.client.force_login(self.admin)
        create_url = reverse('dashboard:stock_ledger:transfer_create')
        self.client.post(create_url, {
            'product': self.product.id, 'from_branch': self.blr.id, 'to_branch': self.maa.id, 'quantity': 30,
        })
        transfer = StockTransfer.objects.get()
        self.assertEqual(transfer.status, StockTransfer.PENDING)

        blr_stock = BranchStock.objects.get(product=self.product, branch=self.blr)
        self.assertEqual(blr_stock.quantity, 100)

        # Dispatch as sending branch staff
        self.client.force_login(self.blr_staff)
        dispatch_url = reverse('dashboard:stock_ledger:transfer_dispatch', args=[transfer.pk])
        response = self.client.post(dispatch_url)
        self.assertEqual(response.json()['success'], True)

        blr_stock.refresh_from_db()
        self.assertEqual(blr_stock.quantity, 70)
        maa_stock, _ = BranchStock.objects.get_or_create(product=self.product, branch=self.maa)
        self.assertEqual(maa_stock.quantity, 0)  # in transit, not yet received

        # Double-dispatch (retry/double-click) must not double-deduct
        response = self.client.post(dispatch_url)
        self.assertEqual(response.json()['success'], False)
        blr_stock.refresh_from_db()
        self.assertEqual(blr_stock.quantity, 70)

        # Receive (fully) as receiving branch staff
        self.client.force_login(self.maa_staff)
        receive_url = reverse('dashboard:stock_ledger:transfer_record_receipt', args=[transfer.pk])
        response = self.client.post(receive_url, data=json.dumps({'quantity': 30}), content_type='application/json')
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['status'], StockTransfer.RECEIVED)
        maa_stock.refresh_from_db()
        self.assertEqual(maa_stock.quantity, 30)

        # A further receipt attempt must not double-add (transfer already closed)
        response = self.client.post(receive_url, data=json.dumps({'quantity': 1}), content_type='application/json')
        self.assertEqual(response.json()['success'], False)
        maa_stock.refresh_from_db()
        self.assertEqual(maa_stock.quantity, 30)

    def test_receiving_branch_staff_cannot_dispatch_someone_elses_transfer(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:stock_ledger:transfer_create'), {
            'product': self.product.id, 'from_branch': self.blr.id, 'to_branch': self.maa.id, 'quantity': 10,
        })
        transfer = StockTransfer.objects.get()

        self.client.force_login(self.maa_staff)
        response = self.client.post(reverse('dashboard:stock_ledger:transfer_dispatch', args=[transfer.pk]))
        self.assertEqual(response.status_code, 403)


class RecomputeBranchStockTests(StockLedgerTestBase):
    def test_recompute_reflects_edit_and_soft_delete(self):
        entry = StockPurchase.objects.create(
            product=self.product, branch=self.blr, quantity=20, price=5, created_by=self.admin,
        )
        recompute_branch_stock(self.product.id, self.blr.id)
        stock = BranchStock.objects.get(product=self.product, branch=self.blr)
        self.assertEqual(stock.quantity, 20)

        entry.quantity = 50
        entry.save()
        recompute_branch_stock(self.product.id, self.blr.id)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 50)

        entry.soft_delete(self.admin)
        recompute_branch_stock(self.product.id, self.blr.id)
        stock.refresh_from_db()
        self.assertEqual(stock.quantity, 0)

    def test_sale_reduces_computed_stock(self):
        StockPurchase.objects.create(product=self.product, branch=self.blr, quantity=20, price=5, created_by=self.admin)
        recompute_branch_stock(self.product.id, self.blr.id)
        StockSale.objects.create(
            product=self.product, branch=self.blr, quantity=6, price=5, selling_price=8, created_by=self.admin,
        )
        recompute_branch_stock(self.product.id, self.blr.id)
        stock = BranchStock.objects.get(product=self.product, branch=self.blr)
        self.assertEqual(stock.quantity, 14)


class ProductSkuIdentityTests(StockLedgerTestBase):
    def test_same_sku_different_brand_allowed(self):
        other_brand = Brand.objects.create(name='NSK', slug='nsk')
        Product.objects.create(
            category=self.category, brand=other_brand, name='6001-ZZ NSK', slug='6001-zz-nsk', sku='6001-ZZ',
        )
        self.assertEqual(Product.objects.filter(sku='6001-ZZ').count(), 2)

    def test_same_sku_same_brand_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    category=self.category, brand=self.brand, name='Duplicate', slug='dup-6001-zz', sku='6001-ZZ',
                )


class SaleStockLimitTests(StockLedgerTestBase):
    def setUp(self):
        super().setUp()
        OpeningStock.objects.create(product=self.product, branch=self.blr, quantity=10, price=5, created_by=self.admin)
        recompute_branch_stock(self.product.id, self.blr.id)

    def test_sale_exceeding_stock_is_rejected(self):
        self.client.force_login(self.blr_staff)
        response = self.client.post(reverse('dashboard:stock_ledger:sale_add'), {
            'sale_date': '2026-01-01', 'customer': '', 'notes': '',
            'item_product': [str(self.product.id)], 'item_quantity': ['11'],
            'item_price': ['5'], 'item_selling_price': ['8'],
        })
        self.assertEqual(response.status_code, 200)  # re-rendered form, not redirected
        self.assertEqual(StockSale.objects.count(), 0)
        stock = BranchStock.objects.get(product=self.product, branch=self.blr)
        self.assertEqual(stock.quantity, 10)

    def test_sale_within_stock_succeeds_and_never_goes_negative(self):
        self.client.force_login(self.blr_staff)
        response = self.client.post(reverse('dashboard:stock_ledger:sale_add'), {
            'sale_date': '2026-01-01', 'customer': '', 'notes': '',
            'item_product': [str(self.product.id)], 'item_quantity': ['10'],
            'item_price': ['5'], 'item_selling_price': ['8'],
        })
        self.assertEqual(response.status_code, 302)
        stock = BranchStock.objects.get(product=self.product, branch=self.blr)
        self.assertEqual(stock.quantity, 0)
        self.assertGreaterEqual(stock.quantity, 0)

    def test_transfer_exceeding_stock_is_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('dashboard:stock_ledger:transfer_create'), {
            'product': self.product.id, 'from_branch': self.blr.id, 'to_branch': self.maa.id, 'quantity': 999,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(StockTransfer.objects.count(), 0)


class TransferPartialReceiptTests(StockLedgerTestBase):
    def setUp(self):
        super().setUp()
        OpeningStock.objects.create(product=self.product, branch=self.blr, quantity=100, price=10, created_by=self.admin)
        recompute_branch_stock(self.product.id, self.blr.id)
        self.client.force_login(self.admin)
        self.client.post(reverse('dashboard:stock_ledger:transfer_create'), {
            'product': self.product.id, 'from_branch': self.blr.id, 'to_branch': self.maa.id, 'quantity': 50,
        })
        self.transfer = StockTransfer.objects.get()
        self.client.force_login(self.blr_staff)
        self.client.post(reverse('dashboard:stock_ledger:transfer_dispatch', args=[self.transfer.pk]))
        self.transfer.refresh_from_db()

    def _receive(self, quantity):
        self.client.force_login(self.maa_staff)
        return self.client.post(
            reverse('dashboard:stock_ledger:transfer_record_receipt', args=[self.transfer.pk]),
            data=json.dumps({'quantity': quantity}), content_type='application/json',
        )

    def test_partial_then_full_receipt_closes_transfer(self):
        response = self._receive(20)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['status'], StockTransfer.PARTIALLY_RECEIVED)
        self.assertEqual(body['remaining_quantity'], 30)
        maa_stock = BranchStock.objects.get(product=self.product, branch=self.maa)
        self.assertEqual(maa_stock.quantity, 20)

        response = self._receive(30)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['status'], StockTransfer.RECEIVED)
        maa_stock.refresh_from_db()
        self.assertEqual(maa_stock.quantity, 50)

    def test_receipt_cannot_exceed_remaining(self):
        response = self._receive(999)
        self.assertFalse(response.json()['success'])
        self.assertEqual(StockTransfer.objects.get(pk=self.transfer.pk).received_quantity, 0)

    def test_not_received_moves_to_issue_reported_and_admin_resolves(self):
        self.client.force_login(self.maa_staff)
        response = self.client.post(
            reverse('dashboard:stock_ledger:transfer_report_not_received', args=[self.transfer.pk])
        )
        self.assertTrue(response.json()['success'])
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, StockTransfer.ISSUE_REPORTED)

        # Branch staff cannot resolve issues — Admin only.
        response = self.client.post(
            reverse('dashboard:stock_ledger:transfer_resolve_issue', args=[self.transfer.pk])
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('dashboard:stock_ledger:transfer_resolve_issue', args=[self.transfer.pk])
        )
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['status'], StockTransfer.DISPATCHED)


class ProductQuickCreateTests(StockLedgerTestBase):
    def test_quick_create_defaults_to_uncategorized(self):
        self.client.force_login(self.blr_staff)
        response = self.client.post(reverse('dashboard:stock_ledger:product_quick_create'), {
            'code': '6205-2RS', 'brand': self.brand.id, 'name': '',
        })
        body = response.json()
        self.assertTrue(body['success'])
        product = Product.objects.get(sku='6205-2RS', brand=self.brand)
        self.assertEqual(product.category.slug, 'uncategorized')
        self.assertEqual(product.name, '6205-2RS')

    def test_quick_create_is_idempotent_for_existing_sku_brand(self):
        self.client.force_login(self.blr_staff)
        first = self.client.post(reverse('dashboard:stock_ledger:product_quick_create'), {
            'code': '6001-ZZ', 'brand': self.brand.id,
        }).json()
        # Same (sku, brand) as self.product created in setUp — should return it, not duplicate.
        self.assertEqual(first['product']['id'], self.product.id)
        self.assertEqual(Product.objects.filter(sku='6001-ZZ', brand=self.brand).count(), 1)

    def test_viewer_cannot_quick_create(self):
        self.client.force_login(self.viewer)
        response = self.client.post(reverse('dashboard:stock_ledger:product_quick_create'), {
            'code': 'X', 'brand': self.brand.id,
        })
        self.assertEqual(response.status_code, 403)


class ProductSearchTests(StockLedgerTestBase):
    def test_search_restricted_to_in_stock_branch(self):
        OpeningStock.objects.create(product=self.product, branch=self.blr, quantity=5, price=1, created_by=self.admin)
        recompute_branch_stock(self.product.id, self.blr.id)

        self.client.force_login(self.blr_staff)
        url = reverse('dashboard:stock_ledger:product_search')
        response = self.client.get(url, {'q': '6001', 'in_stock_branch': self.blr.id})
        self.assertEqual(len(response.json()['results']), 1)

        response = self.client.get(url, {'q': '6001', 'in_stock_branch': self.maa.id})
        self.assertEqual(len(response.json()['results']), 0)


class OpeningStockImportTests(StockLedgerTestBase):
    def test_new_sku_brand_is_auto_created_not_skipped(self):
        upload = make_workbook_upload([['NEW-SKU-1', self.brand.name, self.category.name, self.blr.name, 10, 5, '']])
        result = import_opening_stock_workbook(upload, self.admin)

        self.assertEqual(result.imported, 1)
        self.assertEqual(result.created_products, 1)
        self.assertEqual(result.skipped, 0)
        product = Product.objects.get(sku='NEW-SKU-1', brand=self.brand)
        self.assertEqual(product.category_id, self.category.id)
        stock = BranchStock.objects.get(product=product, branch=self.blr)
        self.assertEqual(stock.quantity, 10)

    def test_new_category_is_auto_created(self):
        self.assertFalse(Category.objects.filter(name='Brand New Category').exists())
        upload = make_workbook_upload([['NEW-SKU-2', self.brand.name, 'Brand New Category', self.blr.name, 10, 5, '']])
        result = import_opening_stock_workbook(upload, self.admin)

        self.assertEqual(result.imported, 1)
        self.assertEqual(result.created_categories, 1)
        product = Product.objects.get(sku='NEW-SKU-2', brand=self.brand)
        self.assertEqual(product.category.name, 'Brand New Category')

    def test_location_is_captured_on_branch_stock(self):
        upload = make_workbook_upload([['NEW-SKU-3', self.brand.name, self.category.name, self.blr.name, 10, 5, 'C1R2']])
        import_opening_stock_workbook(upload, self.admin)
        product = Product.objects.get(sku='NEW-SKU-3', brand=self.brand)
        stock = BranchStock.objects.get(product=product, branch=self.blr)
        self.assertEqual(stock.location, 'C1R2')

    def test_dynamic_spec_columns_are_merged_into_product_specifications(self):
        upload = make_workbook_upload(
            [['NEW-SKU-4', self.brand.name, self.category.name, self.blr.name, 10, 5, '', '12mm', '28mm']],
            extra_headers=['Bore Diameter', 'Outer Diameter'],
        )
        import_opening_stock_workbook(upload, self.admin)
        product = Product.objects.get(sku='NEW-SKU-4', brand=self.brand)
        self.assertEqual(product.specifications.get('Bore Diameter'), '12mm')
        self.assertEqual(product.specifications.get('Outer Diameter'), '28mm')

    def test_reupload_of_already_added_product_is_flagged_as_duplicate_not_error(self):
        OpeningStock.objects.create(
            product=self.product, branch=self.blr, quantity=50, price=10, created_by=self.admin,
        )
        recompute_branch_stock(self.product.id, self.blr.id)

        upload = make_workbook_upload([[self.product.sku, self.brand.name, self.category.name, self.blr.name, 999, 1, '']])
        result = import_opening_stock_workbook(upload, self.admin)

        self.assertEqual(result.imported, 0)
        self.assertEqual(len(result.duplicates), 1)
        self.assertEqual(len(result.errors), 0)
        self.assertIn('already', result.duplicates[0][1].lower())

        # stock must be unaffected by the duplicate attempt
        stock = BranchStock.objects.get(product=self.product, branch=self.blr)
        self.assertEqual(stock.quantity, 50)

    def test_unknown_brand_is_still_skipped_as_error_not_auto_created(self):
        upload = make_workbook_upload([['SOME-SKU', 'TotallyMadeUpBrand', self.category.name, self.blr.name, 10, 5, '']])
        result = import_opening_stock_workbook(upload, self.admin)

        self.assertEqual(result.imported, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertFalse(Brand.objects.filter(name='TotallyMadeUpBrand').exists())

    def test_existing_product_without_opening_stock_at_branch_still_imports(self):
        # Product exists (created in setUp) but has no opening stock at MAA yet.
        upload = make_workbook_upload([[self.product.sku, self.brand.name, self.category.name, self.maa.name, 7, 3, '']])
        result = import_opening_stock_workbook(upload, self.admin)

        self.assertEqual(result.imported, 1)
        self.assertEqual(result.created_products, 0)  # product already existed
        stock = BranchStock.objects.get(product=self.product, branch=self.maa)
        self.assertEqual(stock.quantity, 7)


class MultiItemPurchaseTests(StockLedgerTestBase):
    def test_single_purchase_creates_one_row_per_item_sharing_supplier_and_notes(self):
        other_product = Product.objects.create(
            category=self.category, brand=self.brand, name='6205-2RS', slug='6205-2rs', sku='6205-2RS',
        )
        self.client.force_login(self.blr_staff)
        response = self.client.post(reverse('dashboard:stock_ledger:purchase_add'), {
            'purchase_date': '2026-02-01', 'supplier': 'Blinkit', 'notes': 'Bulk restock order',
            'item_product': [str(self.product.id), str(other_product.id)],
            'item_quantity': ['20', '15'],
            'item_price': ['10.00', '25.50'],
        })
        self.assertEqual(response.status_code, 302)
        entries = StockPurchase.objects.filter(supplier='Blinkit').order_by('id')
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(e.notes == 'Bulk restock order' for e in entries))
        self.assertTrue(all(e.purchase_date.isoformat() == '2026-02-01' for e in entries))

        stock1 = BranchStock.objects.get(product=self.product, branch=self.blr)
        stock2 = BranchStock.objects.get(product=other_product, branch=self.blr)
        self.assertEqual(stock1.quantity, 20)
        self.assertEqual(stock2.quantity, 15)

    def test_incomplete_rows_are_silently_skipped(self):
        self.client.force_login(self.blr_staff)
        response = self.client.post(reverse('dashboard:stock_ledger:purchase_add'), {
            'purchase_date': '2026-02-01', 'supplier': 'Blinkit', 'notes': '',
            'item_product': [str(self.product.id), ''],
            'item_quantity': ['5', ''],
            'item_price': ['10.00', ''],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StockPurchase.objects.filter(supplier='Blinkit').count(), 1)

    def test_no_items_at_all_reports_error_without_crashing(self):
        self.client.force_login(self.blr_staff)
        response = self.client.post(reverse('dashboard:stock_ledger:purchase_add'), {
            'purchase_date': '2026-02-01', 'supplier': 'Blinkit', 'notes': '',
            'item_product': [''], 'item_quantity': [''], 'item_price': [''],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(StockPurchase.objects.count(), 0)


class SaleAddPageTests(StockLedgerTestBase):
    """Regression coverage for the GET-request crash: the template referenced
    `posted` as a filter *argument* (`default:posted.x`), which — unlike a
    plain top-level `{{ posted.x }}` — isn't protected by Django's silent
    missing-variable handling, so it 500'd whenever `posted` wasn't in the
    render context (i.e. every normal page load, not just the error path)."""
    def test_add_sale_page_loads_without_posted_in_context(self):
        self.client.force_login(self.blr_staff)
        response = self.client.get(reverse('dashboard:stock_ledger:sale_add'))
        self.assertEqual(response.status_code, 200)

    def test_add_purchase_page_loads_without_posted_in_context(self):
        self.client.force_login(self.blr_staff)
        response = self.client.get(reverse('dashboard:stock_ledger:purchase_add'))
        self.assertEqual(response.status_code, 200)


class MultiItemSaleTests(StockLedgerTestBase):
    def setUp(self):
        super().setUp()
        self.other_product = Product.objects.create(
            category=self.category, brand=self.brand, name='6205-2RS', slug='6205-2rs', sku='6205-2RS',
        )
        OpeningStock.objects.create(product=self.product, branch=self.blr, quantity=20, price=5, created_by=self.admin)
        OpeningStock.objects.create(product=self.other_product, branch=self.blr, quantity=15, price=8, created_by=self.admin)
        recompute_branch_stock(self.product.id, self.blr.id)
        recompute_branch_stock(self.other_product.id, self.blr.id)

    def test_single_sale_creates_one_row_per_item_sharing_customer_and_notes(self):
        self.client.force_login(self.blr_staff)
        response = self.client.post(reverse('dashboard:stock_ledger:sale_add'), {
            'sale_date': '2026-03-01', 'customer': 'Walk-in', 'notes': 'Counter sale',
            'item_product': [str(self.product.id), str(self.other_product.id)],
            'item_quantity': ['5', '3'],
            'item_price': ['5.00', '8.00'],
            'item_selling_price': ['9.00', '14.00'],
        })
        self.assertEqual(response.status_code, 302)
        entries = StockSale.objects.filter(customer='Walk-in').order_by('id')
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(e.notes == 'Counter sale' for e in entries))

        stock1 = BranchStock.objects.get(product=self.product, branch=self.blr)
        stock2 = BranchStock.objects.get(product=self.other_product, branch=self.blr)
        self.assertEqual(stock1.quantity, 15)  # 20 - 5
        self.assertEqual(stock2.quantity, 12)  # 15 - 3

    def test_sum_of_rows_for_same_product_cannot_exceed_stock(self):
        self.client.force_login(self.blr_staff)
        # Two rows for the same product (20 in stock): 12 + 12 = 24 > 20, must be rejected as a whole.
        response = self.client.post(reverse('dashboard:stock_ledger:sale_add'), {
            'sale_date': '2026-03-01', 'customer': '', 'notes': '',
            'item_product': [str(self.product.id), str(self.product.id)],
            'item_quantity': ['12', '12'],
            'item_price': ['5.00', '5.00'],
            'item_selling_price': ['9.00', '9.00'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(StockSale.objects.count(), 0)
        stock = BranchStock.objects.get(product=self.product, branch=self.blr)
        self.assertEqual(stock.quantity, 20)  # untouched

    def test_incomplete_item_row_is_silently_skipped(self):
        self.client.force_login(self.blr_staff)
        response = self.client.post(reverse('dashboard:stock_ledger:sale_add'), {
            'sale_date': '2026-03-01', 'customer': '', 'notes': '',
            'item_product': [str(self.product.id), ''],
            'item_quantity': ['2', ''],
            'item_price': ['5.00', ''],
            'item_selling_price': ['9.00', ''],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StockSale.objects.count(), 1)
