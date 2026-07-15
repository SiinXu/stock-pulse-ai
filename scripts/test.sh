#!/bin/bash
# ===================================
# Multi-market stock analysis system test script
# ===================================
#
# Usage:
#   ./scripts/test.sh [scenario]
#
# Scenarios:
#   market      - Market review only
#   a-stock     - China A-share analysis (Kweichow Moutai and Ping An Bank)
#   etf         - ETF analysis (Satellite Communications ETF, 563230)
#   hk-stock    - Hong Kong stock analysis (Tencent and Alibaba)
#   us-stock    - US stock analysis (Apple and Tesla)
#   mixed       - Mixed-market analysis
#   single      - Single-stock notification mode
#   dry-run     - Fetch data without running AI analysis
#   full        - Complete workflow test
#   quick       - Quick single-stock test
#   all         - Run all tests
#
# Examples:
#   ./scripts/test.sh market      # Test the market review
#   ./scripts/test.sh us-stock    # Test US stock analysis
#   ./scripts/test.sh quick       # Run the quick test
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

# Terminal colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print color-coded messages.
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

header() {
    echo ""
    echo "=============================================="
    echo -e "${GREEN}$1${NC}"
    echo "=============================================="
    echo ""
}

# Check the Python environment.
check_python() {
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is not installed"
        exit 1
    fi
    info "Python version: $(python3 --version)"
}

# Check dependencies.
check_deps() {
    info "Checking dependencies..."
    python3 -c "import yfinance" 2>/dev/null || { warn "yfinance is not installed; US stock tests may fail"; }
    python3 -c "import akshare" 2>/dev/null || { warn "akshare is not installed; China A-share and Hong Kong stock tests may fail"; }
    success "Dependency check completed"
}

# ==================== Test scenarios ====================

# Test 1: Market review
test_market() {
    header "Test scenario: Market review"
    info "Running market review analysis..."
    python3 main.py --market-review "$@"
    success "Market review test completed"
}

# Test 2: China A-share analysis
test_a_stock() {
    header "Test scenario: China A-share analysis"
    info "Analyzing China A-shares: 600519 (Kweichow Moutai), 000001 (Ping An Bank)"
    python3 main.py --stocks 600519,000001  --no-market-review "$@"
    success "China A-share analysis test completed"
}

# Test 2.5: ETF analysis
test_etf() {
    header "Test scenario: ETF analysis"
    info "Analyzing ETFs: 563230 (Satellite Communications ETF), 512400"
    python3 main.py --stocks 563230,512400 --no-market-review "$@"
    success "ETF analysis test completed"
}

# Test 3: Hong Kong stock analysis
test_hk_stock() {
    header "Test scenario: Hong Kong stock analysis"
    info "Analyzing Hong Kong stocks: hk00700 (Tencent), hk09988 (Alibaba)"
    python3 main.py --stocks hk00700,hk09988 --no-market-review "$@"
    success "Hong Kong stock analysis test completed"
}

# Test 4: US stock analysis
test_us_stock() {
    header "Test scenario: US stock analysis"
    info "Analyzing US stock: AAPL (Apple)"
    # Forward caller arguments; notifications remain enabled unless explicitly disabled.
    python3 main.py --stocks AAPL --no-market-review "$@"
    success "US stock analysis test completed"
}

# Test 5: Mixed-market analysis
test_mixed() {
    header "Test scenario: Mixed-market analysis"
    info "Analyzing mixed markets: 600519 (China A-share), hk00700 (Hong Kong), AAPL (US)"
    python3 main.py --stocks 600519,hk00700,AAPL --no-market-review
    success "Mixed-market analysis test completed"
}

# Test 6: Single-stock notification mode
test_single() {
    header "Test scenario: Single-stock notification mode"
    info "Testing single-stock notification mode..."
    python3 main.py --stocks 600519 --single-notify --no-market-review
    success "Single-stock notification test completed"
}

# Test 7: Dry-run mode
test_dry_run() {
    header "Test scenario: Dry-run mode"
    info "Fetching data without running AI analysis..."
    python3 main.py --stocks 600519,AAPL --dry-run --no-notify
    success "Dry-run test completed"
}

# Test 8: Complete workflow
test_full() {
    header "Test scenario: Complete workflow"
    info "Running the complete stock and market analysis workflow..."
    python3 main.py --stocks 600519 --no-notify
    success "Complete workflow test completed"
}

# Test 9: Quick test
test_quick() {
    header "Test scenario: Quick test"
    info "Running a quick single-stock test..."
    python3 main.py --stocks 600519 --no-market-review --no-notify "$@"
    success "Quick test completed"
}

# Test 10: Symbol recognition
test_code_recognition() {
    header "Test scenario: Symbol recognition"
    info "Testing stock symbol recognition..."

    python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')
from data_provider.akshare_fetcher import _is_hk_code, _is_us_code

test_cases = [
    # (symbol, expected_hk, expected_us, description)
    ("AAPL", False, True, "US - Apple"),
    ("TSLA", False, True, "US - Tesla"),
    ("BRK.B", False, True, "US - Berkshire Hathaway B"),
    ("hk00700", True, False, "Hong Kong - Tencent"),
    ("HK09988", True, False, "Hong Kong - Alibaba"),
    ("600519", False, False, "China A-share - Kweichow Moutai"),
    ("000001", False, False, "China A-share - Ping An Bank"),
]

print("\nStock symbol recognition test:")
print("-" * 60)
all_pass = True
for code, exp_hk, exp_us, desc in test_cases:
    is_hk = _is_hk_code(code)
    is_us = _is_us_code(code)
    hk_ok = is_hk == exp_hk
    us_ok = is_us == exp_us
    status = "✅" if (hk_ok and us_ok) else "❌"
    all_pass = all_pass and hk_ok and us_ok
    print(f"{status} {code:10} | HK:{is_hk:5} US:{is_us:5} | {desc}")

print("-" * 60)
print(f"{'✅ All tests passed!' if all_pass else '❌ Some tests failed!'}")
sys.exit(0 if all_pass else 1)
PYTEST

    success "Symbol recognition test completed"
}

# Test 11: YFinance symbol conversion
test_yfinance_convert() {
    header "Test scenario: YFinance symbol conversion"
    info "Testing YFinance symbol conversion..."

    python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')
from data_provider.yfinance_fetcher import YfinanceFetcher

fetcher = YfinanceFetcher()

test_cases = [
    ("AAPL", "AAPL", "US stock"),
    ("tsla", "TSLA", "lowercase US stock"),
    ("BRK.B", "BRK.B", "US stock with a class suffix"),
    ("hk00700", "0700.HK", "Hong Kong stock"),
    ("HK09988", "9988.HK", "uppercase Hong Kong stock"),
    ("600519", "600519.SS", "Shanghai A-share"),
    ("000001", "000001.SZ", "Shenzhen A-share"),
    ("300750", "300750.SZ", "ChiNext A-share"),
]

print("\nYFinance symbol conversion test:")
print("-" * 60)
all_pass = True
for input_code, expected, desc in test_cases:
    result = fetcher._convert_stock_code(input_code)
    status = "✅" if result == expected else "❌"
    all_pass = all_pass and (result == expected)
    print(f"{status} {input_code:10} -> {result:12} (expected: {expected:12}) | {desc}")

print("-" * 60)
print(f"{'✅ All tests passed!' if all_pass else '❌ Some tests failed!'}")
sys.exit(0 if all_pass else 1)
PYTEST

    success "YFinance symbol conversion test completed"
}

# Test 12: Syntax check
test_syntax() {
    header "Test scenario: Python syntax check"
    info "Checking Python syntax..."

    python3 -m py_compile main.py src/config.py src/notification.py \
        data_provider/akshare_fetcher.py \
        data_provider/yfinance_fetcher.py \
        bot/commands/analyze.py

    success "Syntax check passed"
}

# Test 13: Flake8 static checks
test_flake8() {
    header "Test scenario: Flake8 static checks"
    info "Running Flake8 critical error checks..."

    if command -v flake8 &> /dev/null; then
        flake8 main.py src/config.py src/notification.py --select=F821,E999 --max-line-length=120
        success "Flake8 checks passed"
    else
        warn "Flake8 is not installed; skipping checks"
    fi
}

# Run all tests.
test_all() {
    header "Run all tests"

    test_syntax
    test_code_recognition
    test_yfinance_convert
    test_flake8

    echo ""
    info "The following tests require network access and API configuration and may fail:"
    echo ""

    test_dry_run || warn "Dry-run test failed (possibly a network issue)"
    test_quick || warn "Quick test failed (possibly an API configuration issue)"

    success "All tests completed!"
}

# ==================== Main entrypoint ====================

main() {
    header "Multi-market stock analysis test suite"

    check_python
    check_deps

    case "${1:-help}" in
        market)
            shift
            test_market "$@"
            ;;
        a-stock|a_stock|astock)
            shift
            test_a_stock "$@"
            ;;
        etf)
            shift
            test_etf "$@"
            ;;
        hk-stock|hk_stock|hkstock|hk)
            shift
            test_hk_stock "$@"
            ;;
        us-stock|us_stock|usstock|us)
            shift
            test_us_stock "$@"
            ;;
        mixed|mix)
            shift
            test_mixed "$@"
            ;;
        single)
            shift
            test_single "$@"
            ;;
        dry-run|dryrun|dry)
            shift
            test_dry_run "$@"
            ;;
        full)
            shift
            test_full "$@"
            ;;
        quick|q)
            shift
            test_quick "$@"
            ;;
        code|recognition)
            shift
            test_code_recognition "$@"
            ;;
        yfinance|yf)
            shift
            test_yfinance_convert "$@"
            ;;
        syntax)
            shift
            test_syntax "$@"
            ;;
        flake8|lint)
            shift
            test_flake8 "$@"
            ;;
        all)
            shift
            test_all "$@"
            ;;
        help|--help|-h|*)
            echo "Usage: $0 [scenario]"
            echo ""
            echo "Scenarios:"
            echo "  market      - Market review only"
            echo "  a-stock     - China A-share analysis"
            echo "  etf         - ETF analysis"
            echo "  hk-stock    - Hong Kong stock analysis"
            echo "  us-stock    - US stock analysis"
            echo "  mixed       - Mixed-market analysis"
            echo "  single      - Single-stock notification mode"
            echo "  dry-run     - Fetch data without AI analysis"
            echo "  full        - Complete workflow"
            echo "  quick       - Quick test (recommended)"
            echo "  code        - Symbol recognition test"
            echo "  yfinance    - YFinance symbol conversion test"
            echo "  syntax      - Syntax check"
            echo "  flake8      - Static checks"
            echo "  all         - Run all tests"
            echo ""
            echo "Examples:"
            echo "  $0 quick     # Run the quick test"
            echo "  $0 us-stock  # Test US stock analysis"
            echo "  $0 code      # Test symbol recognition"
            echo "  $0 all       # Run all tests"
            ;;
    esac
}

main "$@"
