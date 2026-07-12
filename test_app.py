"""
Test script for L&P_Freight app.py
Verifies that all imports resolve correctly and basic structure is sound.
"""
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

print(f"Python: {sys.executable}")
print(f"Project root: {PROJECT_ROOT}")
print(f"Python version: {sys.version}")
print()

# Test 1: Check that lp_helpers package is importable
print("=" * 60)
print("TEST 1: Import lp_helpers.database")
print("=" * 60)
try:
    from lp_helpers.database import DB_PATH, init_db, seed_assets
    print(f"  ✓ DB_PATH = {DB_PATH}")
    print(f"  ✓ init_db = {init_db}")
    print(f"  ✓ seed_assets = {seed_assets}")
except ImportError as e:
    print(f"  ✗ FAILED: {e}")

print()

# Test 2: Check that all app.py imports resolve
print("=" * 60)
print("TEST 2: Import all modules used in app.py")
print("=" * 60)

imports_to_test = [
    ("lp_helpers.database", ["DB_PATH", "init_db", "seed_assets"]),
    ("lp_helpers.pay_engine", ["pay_decision"]),
    ("routing_editor", ["ingest_eld_miles"]),
    ("lp_helpers.ui_theme", ["inject_mobile_css", "render_bottom_nav", "SCREENS", "empty_state"]),
    ("lp_helpers.fleet", ["get_fleet_view"]),
    ("lp_helpers.notifications", ["get_notifications", "dismiss_notification", "CATEGORY_META"]),
    ("lp_helpers.driver", ["get_driver_hos", "get_driver_loads", "accept_load", "save_bol_photo"]),
    ("lp_helpers.billing", ["generate_invoice_pdf", "fetch_load", "mark_invoice_sent"]),
    ("lp_helpers.recommend", ["get_recommendations"]),
    ("lp_helpers.loadboard", ["fetch_board_loads", "filter_board", "assign_load", "board_status_options", "board_shipper_options"]),
    ("lp_helpers.offline_resilience", ["render_offline_banner", "lazy_render", "disk_cache", "invalidate_cache"]),
    ("lp_helpers.global_search", ["render_global_search_bar", "render_search_results_modal"]),
    ("lp_helpers.bi_analytics", ["render_bi_analytics_page"]),
    ("lp_helpers.brokerage_authority", ["render_brokerage_authority_widget", "seed_brokerage_authority_items"]),
    ("lp_helpers.customer_booking", ["render_customer_booking_form", "render_dispatcher_review_panel", "ensure_dispatch_requests_table", "get_pending_dispatch_count"]),
    ("lp_helpers.document_vault", ["render_document_vault", "ensure_documents_table"]),
    ("lp_helpers.eld_providers", ["create_best_eld_provider", "SamsaraProvider", "MotiveProvider"]),
    ("eld_integration", ["ELDClient"]),
    ("portal", ["add_po_load", "create_purchase_order", "fetch_customers", "fetch_po_loads", "fetch_purchase_orders", "get_customer_po_summary", "init_customer_portal", "seed_demo_customers", "update_po_load_status", "update_po_status"]),
]

all_passed = True
for module_name, names in imports_to_test:
    try:
        mod = __import__(module_name, fromlist=names)
        for name in names:
            if not hasattr(mod, name):
                print(f"  ✗ {module_name} has no attribute '{name}'")
                all_passed = False
        print(f"  ✓ {module_name} -> {', '.join(names)}")
    except ImportError as e:
        print(f"  ✗ {module_name}: {e}")
        all_passed = False

print()

# Test 3: Check that app.py can be parsed (syntax check)
print("=" * 60)
print("TEST 3: Syntax check app.py")
print("=" * 60)
app_path = os.path.join(PROJECT_ROOT, "app.py")
try:
    with open(app_path, "r", encoding="utf-8") as f:
        source = f.read()
    compile(source, app_path, "exec")
    print(f"  ✓ app.py syntax is valid")
except SyntaxError as e:
    print(f"  ✗ Syntax error: {e}")
    all_passed = False

print()
print("=" * 60)
if all_passed:
    print("RESULT: ALL TESTS PASSED ✓")
else:
    print("RESULT: SOME TESTS FAILED ✗")
print("=" * 60)