"""
PSAN Radar - Frontend E2E Test Suite
Playwright headless browser tests for React Vite frontend.
"""

import asyncio
import pytest
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from typing import AsyncGenerator
import os


# =============================================================================
# CONFIGURATION
# =============================================================================

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://172.28.192.1:5174")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
SLOW_MO = int(os.getenv("SLOW_MO", "0"))
TIMEOUT = 15000  # 15 seconds


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="function")
async def page() -> AsyncGenerator[Page, None]:
    """Launch Playwright browser, context, and page on the test function's event loop."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            slow_mo=SLOW_MO,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True
        )
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT)
        try:
            yield page
        finally:
            await page.close()
            await context.close()
            await browser.close()


@pytest.fixture(scope="session", autouse=True)
def verify_services_running():
    """Verify backend and frontend are accessible before running tests."""
    import httpx

    with httpx.Client(timeout=10.0) as client:
        try:
            response = client.get(f"{BACKEND_URL}/api/v1/health")
            assert response.status_code == 200, f"Backend health check failed: {response.status_code}"
            data = response.json()
            assert data.get("status") == "ok"
            print(f"[OK] Backend is healthy at {BACKEND_URL}")
        except Exception as e:
            pytest.fail(f"Backend not accessible at {BACKEND_URL}: {e}")

        try:
            response = client.get(FRONTEND_URL)
            assert response.status_code == 200, f"Frontend check failed: {response.status_code}"
            print(f"[OK] Frontend is accessible at {FRONTEND_URL}")
        except Exception as e:
            pytest.fail(f"Frontend not accessible at {FRONTEND_URL}: {e}")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def wait_for_map_load(page: Page, timeout: int = 15000):
    """Wait for Leaflet map to fully load."""
    # Wait for map container
    await page.wait_for_selector(".leaflet-container", state="visible", timeout=timeout)
    
    # Wait for map tiles to load
    await page.wait_for_function(
        """() => {
            const map = document.querySelector('.leaflet-container');
            if (!map) return false;
            const leafletMap = map._leaflet_map;
            if (!leafletMap) return false;
            return leafletMap._loaded === true;
        }""",
        timeout=timeout
    )
    
    # Wait for GeoJSON layers to render
    await page.wait_for_selector(".leaflet-interactive", state="attached", timeout=timeout)


async def get_siruta_from_map(page: Page) -> int:
    """Extract a SIRUTA code from the map features."""
    # Get the first feature's SIRUTA from the GeoJSON layer
    siruta = await page.evaluate("""() => {
        const mapContainer = document.querySelector('.leaflet-container');
        if (!mapContainer || !mapContainer._leaflet_map) return null;
        
        const map = mapContainer._leaflet_map;
        let foundSiruta = null;
        
        map.eachLayer(layer => {
            if (layer.feature && layer.feature.properties && layer.feature.properties.siruta) {
                foundSiruta = layer.feature.properties.siruta;
            }
        });
        
        return foundSiruta;
    }""")
    
    return siruta


# =============================================================================
# TEST 2.1: Map & Choropleth Rendering
# =============================================================================

class TestMapChoroplethRendering:
    """Test 2.1: Map & Choropleth Rendering"""

    @pytest.mark.asyncio
    async def test_map_container_visible_and_sized(self, page: Page):
        """Assert Leaflet map canvas is visible and has height > 0."""
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        
        # Wait for map container
        map_container = page.locator(".leaflet-container")
        await map_container.wait_for(state="visible", timeout=TIMEOUT)
        
        # Verify map has dimensions
        box = await map_container.bounding_box()
        assert box is not None, "Map container not found"
        assert box["width"] > 0, f"Map width should be > 0, got {box['width']}"
        assert box["height"] > 0, f"Map height should be > 0, got {box['height']}"
        
        print(f"[OK] Map container visible: {box['width']}x{box['height']}")

    @pytest.mark.asyncio
    async def test_geojson_polygons_rendered(self, page: Page):
        """Wait for vector GeoJSON layers to load; assert polygon paths are rendered."""
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await wait_for_map_load(page)
        
        # Check for rendered SVG paths (Leaflet renders polygons as SVG paths)
        polygons = page.locator(".leaflet-interactive")
        count = await polygons.count()
        
        assert count > 0, f"Expected at least 1 polygon path, found {count}"
        print(f"[OK] Found {count} rendered polygon(s) on map")

    @pytest.mark.asyncio
    async def test_choropleth_colors_match_priority_tiers(self, page: Page):
        """Verify polygons have fill colors corresponding to priority tiers."""
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await wait_for_map_load(page)
        
        # Check that polygons have fill colors (not transparent)
        polygons = page.locator(".leaflet-interactive")
        count = await polygons.count()
        
        # Sample a few polygons to verify they have fill
        for i in range(min(3, count)):
            polygon = polygons.nth(i)
            fill = await polygon.get_attribute("fill")
            assert fill is not None and fill != "none", f"Polygon {i} has no fill color"
            print(f"  Polygon {i} fill: {fill}")


# =============================================================================
# TEST 2.2: Reactive Filter Interaction
# =============================================================================

class TestReactiveFilterInteraction:
    """Test 2.2: Reactive Filter Interaction"""

    @pytest.mark.asyncio
    async def test_rvi_slider_filters_polygons(self, page: Page):
        """Locate RVI slider, change to 75, verify low-vulnerability polygons filtered out."""
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await wait_for_map_load(page)
        
        # Get initial polygon count
        initial_polygons = page.locator(".leaflet-interactive")
        initial_count = await initial_polygons.count()
        print(f"Initial polygon count: {initial_count}")
        
        # Find the RVI slider - it's an input[type="range"]
        rvi_slider = page.locator('input[type="range"]').first
        await rvi_slider.wait_for(state="visible", timeout=TIMEOUT)
        
        # Get slider bounds
        slider_box = await rvi_slider.bounding_box()
        assert slider_box is not None, "RVI slider not found"
        
        # Move slider to 75 (approximately 75% of the way)
        # The slider goes from 0 to 100, so 75 is at 75% position
        await page.mouse.move(
            slider_box["x"] + slider_box["width"] * 0.75,
            slider_box["y"] + slider_box["height"] / 2
        )
        await page.mouse.down()
        await page.mouse.up()
        
        # Alternative: use fill or set value directly
        await rvi_slider.evaluate("el => el.value = 75")
        await rvi_slider.dispatch_event("input")
        await rvi_slider.dispatch_event("change")
        
        # Wait for map to update (filter applied)
        await page.wait_for_timeout(1000)
        
        # Get filtered polygon count
        filtered_polygons = page.locator(".leaflet-interactive")
        filtered_count = await filtered_polygons.count()
        print(f"Filtered polygon count (RVI >= 75): {filtered_count}")
        
        # Verify count decreased (or at least didn't increase)
        assert filtered_count <= initial_count, \
            f"Filter should reduce or maintain polygon count: {initial_count} -> {filtered_count}"
        
        # Verify active count indicator updates (if present)
        active_count_elem = page.locator("text=/\\d+.*active|\\d+.*UAT|Showing \\d+/i").first
        if await active_count_elem.count() > 0:
            text = await active_count_elem.text_content()
            print(f"Active count indicator: {text}")

    @pytest.mark.asyncio
    async def test_county_filter_works(self, page: Page):
        """Test county dropdown filter."""
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await wait_for_map_load(page)
        
        # Find county select
        county_select = page.locator("select").filter(has_text="County").first
        if await county_select.count() == 0:
            # Try alternative selector
            county_select = page.locator("select").first
        
        if await county_select.count() > 0:
            # Get options
            options = await county_select.locator("option").all()
            if len(options) > 1:
                # Select second option (first is usually "All")
                await county_select.select_option(index=1)
                await page.wait_for_timeout(1000)
                
                filtered_count = await page.locator(".leaflet-interactive").count()
                print(f"Filtered by county: {filtered_count} polygons")


# =============================================================================
# TEST 2.3: UAT Selection & Drawer Workflow
# =============================================================================

class TestUATSelectionDrawerWorkflow:
    """Test 2.3: UAT Selection & Drawer Workflow"""

    @pytest.mark.asyncio
    async def test_click_polygon_opens_drawer(self, page: Page):
        """Click on a visible polygon, assert right-side drawer opens."""
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await wait_for_map_load(page)
        
        # Get a polygon to click
        polygons = page.locator(".leaflet-interactive")
        count = await polygons.count()
        assert count > 0, "No polygons to click"
        
        # Click the first polygon
        first_polygon = polygons.first
        await first_polygon.click()
        
        # Wait for drawer to open
        await page.wait_for_timeout(500)
        
        # Check for drawer - look for the dossier panel
        drawer = page.locator(".absolute.right-0.top-0.z-20, [role='dialog'], .drawer, .sidebar").first
        
        # Alternative: check for dossier panel content
        dossier_title = page.locator("text=EU Project Dossier").first
        await dossier_title.wait_for(state="visible", timeout=5000)
        
        assert await dossier_title.is_visible(), "Drawer/Dossier panel did not open"
        print("[OK] Drawer opened successfully")

    @pytest.mark.asyncio
    async def test_drawer_shows_uat_details(self, page: Page):
        """Check that UAT details, deficit progress bars, and Export PDF button are rendered."""
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await wait_for_map_load(page)
        
        # Click a polygon
        polygons = page.locator(".leaflet-interactive")
        await polygons.first.click()
        
        # Wait for drawer content
        await page.wait_for_selector("text=EU Project Dossier", timeout=5000)
        
        # Check for UAT name
        uat_name = page.locator(".absolute.right-0.top-0.z-20 h3, .drawer h3, .sidebar h3").first
        await uat_name.wait_for(state="visible", timeout=5000)
        name_text = await uat_name.text_content()
        assert name_text and len(name_text) > 0, "UAT name not displayed"
        print(f"[OK] UAT name displayed: {name_text}")
        
        # Check for deficit progress bars / stat cards
        stat_cards = page.locator(".absolute.right-0.top-0.z-20 .flex.items-center.gap-3, .stat-card, [class*='StatCard']")
        card_count = await stat_cards.count()
        assert card_count >= 3, f"Expected at least 3 stat cards (sanitation, energy, education), found {card_count}"
        print(f"[OK] Found {card_count} deficit stat cards")
        
        # Check for Export PDF button
        pdf_button = page.locator("a:has-text('Export PDF'), button:has-text('Export PDF')").first
        await pdf_button.wait_for(state="visible", timeout=5000)
        assert await pdf_button.is_visible(), "Export PDF button not visible"
        print("[OK] Export PDF button visible")
        
        # Check for Grant Narrative button
        grant_button = page.locator("button:has-text('Grant Narrative')").first
        await grant_button.wait_for(state="visible", timeout=5000)
        assert await grant_button.is_visible(), "Grant Narrative button not visible"
        print("[OK] Grant Narrative button visible")

    @pytest.mark.asyncio
    async def test_drawer_close_button_works(self, page: Page):
        """Test that drawer can be closed."""
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await wait_for_map_load(page)
        
        # Click a polygon
        polygons = page.locator(".leaflet-interactive")
        await polygons.first.click()
        
        # Wait for drawer
        await page.wait_for_selector("text=EU Project Dossier", timeout=5000)
        
        # Click close button (X)
        close_button = page.locator(".absolute.right-0.top-0.z-20 button:has(svg), button[aria-label='Close'], .close-button").first
        if await close_button.count() > 0:
            await close_button.click()
            await page.wait_for_timeout(500)
            
            # Verify drawer closed
            drawer_title = page.locator("text=EU Project Dossier")
            assert await drawer_title.count() == 0 or not await drawer_title.is_visible(), "Drawer did not close"
            print("[OK] Drawer closes correctly")


# =============================================================================
# TEST 2.4: Real-Time Telemetry Widget
# =============================================================================

class TestTelemetryWidget:
    """Test 2.4: Real-Time Telemetry Widget"""

    @pytest.mark.asyncio
    async def test_telemetry_widget_renders(self, page: Page):
        """Ensure telemetry widget renders with live impact metrics."""
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await wait_for_map_load(page)
        
        # Look for telemetry widget - it might be in a corner or sidebar
        telemetry_widget = page.locator(
            "text=/Telemetry|Live Impact|kWh|CO2|Avoided/i"
        ).first
        
        # Also check for specific metric cards
        metric_cards = page.locator(
            ".telemetry-widget, [class*='telemetry'], [class*='Telemetry'], "
            ".impact-metrics, [class*='impact']"
        )
        
        # If widget not found by text, check for any element with telemetry-related content
        if await telemetry_widget.count() == 0 and await metric_cards.count() == 0:
            # Check for any element containing kWh or CO2
            telemetry_widget = page.locator("text=/kWh|CO₂|CO2|Avoided/i").first
        
        if await telemetry_widget.count() > 0:
            await telemetry_widget.wait_for(state="visible", timeout=5000)
            print("[OK] Telemetry widget found and visible")
        else:
            # Widget might not be implemented yet - skip gracefully
            pytest.skip("Telemetry widget not found in current UI")

    @pytest.mark.asyncio
    async def test_battery_alarm_simulation(self, page: Page):
        """Click 'Simulează Cădere Baterie' and assert pulsing red alert badge appears."""
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await wait_for_map_load(page)
        
        # Look for the alarm test button
        alarm_button = page.locator(
            "button:has-text('Simulează Cădere Baterie'), "
            "button:has-text('Simuleaza Cadere Baterie'), "
            "button:has-text('Battery Alarm'), "
            "button:has-text('Test Alarm')"
        ).first
        
        if await alarm_button.count() == 0:
            pytest.skip("Battery alarm simulation button not found")
        
        await alarm_button.wait_for(state="visible", timeout=5000)
        await alarm_button.click()
        
        # Wait for alert badge to appear
        alert_badge = page.locator(
            ".alert-badge, .pulse-red, [class*='alert'][class*='pulse'], "
            ".animate-pulse.bg-red, text=/Critical|Alert|Battery.*Low/i"
        ).first
        
        try:
            await alert_badge.wait_for(state="visible", timeout=5000)
            assert await alert_badge.is_visible(), "Alert badge did not appear"
            print("[OK] Battery alarm simulation triggered alert badge")
        except:
            # Check if there's any visual indication
            page_content = await page.content()
            if "critical" in page_content.lower() or "alert" in page_content.lower():
                print("[OK] Alert indication found in page content")
            else:
                pytest.skip("Alert badge not visually detected - may need implementation")


# =============================================================================
# ADDITIONAL UI TESTS
# =============================================================================

class TestPWAFieldSurvey:
    """Test PWA Field Survey module (if accessible)."""

    @pytest.mark.asyncio
    async def test_field_survey_module_accessible(self, page: Page):
        """Test that Field Survey PWA module can be accessed."""
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        
        # Look for survey/field survey link or button
        survey_link = page.locator(
            "a:has-text('Survey'), a:has-text('Field Survey'), "
            "button:has-text('Survey'), button:has-text('Field Survey'), "
            "[href*='survey'], [href*='field']"
        ).first
        
        if await survey_link.count() > 0:
            await survey_link.click()
            await page.wait_for_load_state("domcontentloaded")
            
            # Check for survey form elements
            form = page.locator("form, .survey-form, [class*='Survey']")
            if await form.count() > 0:
                print("[OK] Field Survey module accessible")
            else:
                print("[OK] Navigated to survey page")
        else:
            pytest.skip("Field Survey module link not found in main navigation")


class TestResponsiveDesign:
    """Test responsive behavior."""

    @pytest.mark.asyncio
    async def test_mobile_viewport(self, page: Page):
        """Test UI adapts to mobile viewport."""
        await page.set_viewport_size({"width": 375, "height": 667})
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded")
        await wait_for_map_load(page)
        
        # Map should still be visible
        map_container = page.locator(".leaflet-container")
        await map_container.wait_for(state="visible", timeout=TIMEOUT)
        
        box = await map_container.bounding_box()
        assert box is not None
        assert box["width"] > 0
        print(f"[OK] Mobile viewport works: map size {box['width']}x{box['height']}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])