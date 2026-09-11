# Dashboard HTML Audit & Recommendations

**Date:** 2026-09-04  
**File:** `dashboard/templates/dashboard/dashboard.html`  
**Analysis:** Security, Accessibility, Performance, Logic

---

## 🔴 Critical Issues

### 1. **Missing ARIA Labels & Keyboard Navigation**
**Severity:** HIGH | **Category:** Accessibility

**Problem:**
- Toggleable blade elements (`toggleBlade()`) have no `role="button"` or `aria-expanded` states
- Chevron icons (▼/▲) are decorative but not marked as such
- Buttons and form inputs lack descriptive labels
- No keyboard event handlers (Enter/Space to toggle blades)
- Screen reader users cannot understand interactive elements

**Code:**
```html
<div class="blade-head" onclick="toggleBlade('blade-{{ cat.key }}')">
  <span>MF</span>
  <span class="blade-name">Mutual Funds</span>
  <span class="chev" id="chev-blade-mutual_funds">▼</span>
</div>
```

**Fix:**
```html
<div class="blade-head" 
     onclick="toggleBlade('blade-mutual_funds')"
     onkeypress="if(event.key==='Enter'||event.key===' ')toggleBlade('blade-mutual_funds')"
     role="button"
     tabindex="0"
     aria-expanded="false"
     aria-controls="body-blade-mutual_funds">
  <span aria-label="Mutual Funds section">MF</span>
  <span class="blade-name">Mutual Funds</span>
  <span class="chev" id="chev-blade-mutual_funds" aria-hidden="true">▼</span>
</div>
```

---

### 2. **Table Headers Missing Scope Attributes**
**Severity:** MEDIUM | **Category:** Accessibility

**Problem:**
- Table `<th>` elements don't specify `scope="col"` or `scope="row"`
- Screen readers cannot associate header cells with data cells
- Affects 8+ tables throughout dashboard

**Current:**
```html
<thead>
  <tr>
    <th>Fund</th>
    <th class="r">Units</th>
    <th class="r">NAV</th>
  </tr>
</thead>
```

**Fix:**
```html
<thead>
  <tr>
    <th scope="col">Fund</th>
    <th scope="col" class="r">Units</th>
    <th scope="col" class="r">NAV</th>
  </tr>
</thead>
```

---

### 3. **Color-Only Status Indicators**
**Severity:** MEDIUM | **Category:** Accessibility + UX

**Problem:**
- Status badges (`.badge.ok`, `.badge.warn`, `.badge.error`) rely only on color
- Users with color blindness cannot distinguish states
- Insurance status uses only green/yellow/red badges

**Current:**
```html
<span class="badge {{ r.status_level }}">{{ r.status }}</span>
```

**Fix:**
```html
<span class="badge {{ r.status_level }}" title="{{ r.status }}">
  <span class="badge-icon">
    {% if r.status_level == 'ok' %}✓{% elif r.status_level == 'warn' %}⚠{% else %}✕{% endif %}
  </span>
  {{ r.status }}
</span>
```

---

### 4. **External CDN Dependency Risk**
**Severity:** MEDIUM | **Category:** Security + Performance

**Problem:**
- Chart.js loaded from `cdn.jsdelivr.net` (no integrity hash)
- Google Fonts from googleapis (no integrity hash)
- SRI (Subresource Integrity) missing on critical deps
- Falling back gracefully if CDN unavailable

**Current:**
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
```

**Fix:**
```html
<script 
  src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"
  integrity="sha384-<HASH>"
  crossorigin="anonymous"
  onerror="document.body.innerHTML='Charts unavailable. Please refresh.'"
></script>
```

---

## 🟠 Performance Issues

### 5. **All Charts Rendered Immediately**
**Severity:** MEDIUM | **Category:** Performance

**Problem:**
- 8+ charts instantiated on page load even if not visible
- Blade bodies are hidden but charts still render
- No lazy-loading or intersection observer
- Can cause 500ms+ page paint delay on slower devices

**Current:**
```javascript
mkDoughnut('mfBladeChart', mfChart.labels, ...);  // Always runs
mkDoughnut('retBladeChart', retirementData.labels, ...);  // Always runs
```

**Fix:**
```javascript
const observerOptions = { threshold: 0.1 };
const observer = new IntersectionObserver(function(entries) {
  entries.forEach(entry => {
    if (entry.isIntersecting && !entry.target.dataset.charted) {
      const chartId = entry.target.id;
      // Render chart only when visible
      if (chartId === 'mfBladeChart') mkDoughnut(...);
      entry.target.dataset.charted = 'true';
      observer.unobserve(entry.target);
    }
  });
}, observerOptions);

['mfBladeChart', 'retBladeChart', ...].forEach(id => {
  const el = document.getElementById(id);
  if (el) observer.observe(el);
});
```

---

### 6. **Large Inline CSS**
**Severity:** LOW | **Category:** Performance + Maintainability

**Problem:**
- ~1,800 lines of CSS embedded in `<style>` tag (not cacheable)
- Should be external stylesheet for better caching
- Makes HTML 55% larger than needed

**Recommendation:**
- Move CSS to `static/dashboard/dashboard.css`
- Add cache-busting version hash

---

### 7. **No Image Optimization for Gradients**
**Severity:** LOW | **Category:** Performance

**Problem:**
- Heavy use of CSS gradients in every element
- `linear-gradient()` on 50+ elements
- Could use CSS variables to reduce duplication

**Current:**
```css
.card { background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%); }
.blade { background: rgba(255, 255, 255, .95); backdrop-filter: blur(12px); }
/* ... repeated 20+ times */
```

**Fix:**
```css
:root {
  --gradient-bg: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
  --glass: rgba(255, 255, 255, .95);
  --blur: backdrop-filter: blur(12px);
}

.card { background: var(--gradient-bg); }
.blade { background: var(--glass); }
```

---

## 🟡 Logic & Template Issues

### 8. **No Null Checks on Dynamic Data**
**Severity:** MEDIUM | **Category:** Reliability

**Problem:**
- Template assumes `portfolio` always has all properties
- No fallback if `file_info`, `alerts`, or `snapshots` are undefined
- Charts crash silently if data is malformed

**Current:**
```html
{% if portfolio %}
  <div class="hero">
    <div class="nw">₹{{ portfolio.net_worth|floatformat:0 }}</div>
  </div>
{% endif %}
```

**Better:**
```html
{% if portfolio.net_worth %}
  <div class="hero">
    <div class="nw">₹{{ portfolio.net_worth|floatformat:0 }}</div>
  </div>
{% else %}
  <div class="hero" style="background:#fff8c5;border-color:#d4a72c;">
    <span style="color:#9a6700;">Net worth data unavailable</span>
  </div>
{% endif %}
```

---

### 9. **Hardcoded Color Cycles Risk Misalignment**
**Severity:** LOW | **Category:** Logic

**Problem:**
- Uses Django `{% cycle '1' '2' '3' ... %}` for chart segment colors
- If mutual funds list reorders, colors shift but legend doesn't
- Creates confusion: "Fund A shows as green but the legend says it's brown"

**Current:**
```html
<div class="pb-segment seg-mf-{% cycle '1' '2' '3' '4' '5' '6' '7' '8' %}">
```

**Fix:**
```python
# In views.py, pre-assign colors
for idx, fund in enumerate(portfolio.mutual_funds):
    fund['color_class'] = f'seg-mf-{(idx % 8) + 1}'
```

Then in template:
```html
<div class="pb-segment {{ fund.color_class }}">
```

---

### 10. **Empty Trend Chart State**
**Severity:** LOW | **Category:** UX

**Problem:**
- If only 1 snapshot exists, trend chart shows single point
- No message to user about needing more data
- JavaScript tries to calculate deltas that don't exist

**Current:**
```javascript
if(snaps.length>1) {
  // Show stats
}
// But chart renders anyway with 1 point
```

**Better:**
```javascript
if(snaps.length < 2) {
  document.getElementById('trendChart').style.display = 'none';
  document.getElementById('trend-empty').style.display = 'block';
} else {
  // Render chart
}
```

---

## 🟢 Missing Features (Enhancement Requests)

### 11. **Dark Mode**
**Priority:** MEDIUM | **Complexity:** Medium

**Approach:**
```css
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1a1a1a;
    --panel: #2d2d2d;
    --txt: #f5f5f5;
    /* ... */
  }
}

/* Or with toggle button */
body.dark-mode {
  --bg: #1a1a1a;
  /* ... */
}
```

Add toggle button in topbar:
```html
<button class="btn" onclick="document.body.classList.toggle('dark-mode')">
  🌙 Dark Mode
</button>
```

---

### 12. **Export to PDF/Excel**
**Priority:** HIGH | **Complexity:** High

**Approach:**
- Use `html2pdf.js` for PDF export
- Use `xlsx` library for Excel export
- Add button in topbar

```html
<button class="btn" onclick="exportPDF()">📄 PDF</button>
<button class="btn" onclick="exportExcel()">📊 Excel</button>
```

```javascript
function exportPDF() {
  const element = document.querySelector('.page');
  const opt = {
    margin: 10,
    filename: 'portfolio-snapshot.pdf',
    image: { type: 'jpeg', quality: 0.98 },
    html2canvas: { scale: 2 },
    jsPDF: { orientation: 'portrait', unit: 'mm', format: 'a4' }
  };
  html2pdf().set(opt).from(element).save();
}
```

---

### 13. **Date Range Filter on Trend Chart**
**Priority:** MEDIUM | **Complexity:** Medium

**Approach:**
- Add date pickers in `.trend-stats` section
- Filter snapshots array
- Recalculate chart

```html
<div class="trend-stats compact">
  <input type="date" id="trend-start" onchange="updateTrendChart()">
  <input type="date" id="trend-end" onchange="updateTrendChart()">
</div>
```

```javascript
function updateTrendChart() {
  const start = new Date(document.getElementById('trend-start').value);
  const end = new Date(document.getElementById('trend-end').value);
  
  const filtered = snaps.filter(s => {
    const sDate = new Date(s.date);
    return sDate >= start && sDate <= end;
  });
  
  // Recreate chart with filtered data
  trendChart.data.labels = filtered.map(s => s.month);
  trendChart.data.datasets[0].data = filtered.map(s => s.total_net_worth);
  trendChart.update();
}
```

---

### 14. **Download Snapshot as Image**
**Priority:** LOW | **Complexity:** Low

```html
<button class="btn" onclick="downloadSnapshot()">📸 Screenshot</button>
```

```javascript
function downloadSnapshot() {
  html2canvas(document.querySelector('.snapshot')).then(canvas => {
    const link = document.createElement('a');
    link.href = canvas.toDataURL();
    link.download = 'portfolio-snapshot.png';
    link.click();
  });
}
```

---

## 📋 Summary Table

| Issue | Severity | Category | Impact | Fix Complexity |
|-------|----------|----------|--------|-----------------|
| Missing ARIA labels | 🔴 HIGH | Accessibility | Screen reader users blocked | Medium |
| Table scope attributes | 🟠 MEDIUM | Accessibility | Poor semantic HTML | Low |
| Color-only status | 🟠 MEDIUM | Accessibility | Colorblind users confused | Low |
| CDN integrity hashes | 🟠 MEDIUM | Security | Supply chain attack risk | Low |
| All charts render | 🟠 MEDIUM | Performance | Page paint delay | Medium |
| Large inline CSS | 🟡 LOW | Performance | File size, no cache | Medium |
| No null checks | 🟠 MEDIUM | Reliability | Silent failures | Low |
| Color cycle risk | 🟡 LOW | Logic | Misleading legend | Low |
| Empty trend state | 🟡 LOW | UX | Confusing UI | Low |
| **Dark mode** | 🟢 ENHANCEMENT | Feature | User preference | Medium |
| **PDF/Excel export** | 🟢 ENHANCEMENT | Feature | Data portability | High |
| **Date filter** | 🟢 ENHANCEMENT | Feature | Trend analysis | Medium |
| **Screenshot** | 🟢 ENHANCEMENT | Feature | Quick sharing | Low |

---

## Recommended Priority Order

1. **Week 1:** Fix accessibility (ARIA labels, table scope, status indicators)
2. **Week 2:** Add integrity hashes to CDN, lazy-load charts
3. **Week 3:** Implement dark mode + date filter on trend
4. **Week 4:** Add PDF/Excel export

---

## Implementation Roadmap

### Phase 1: Accessibility (4 hours)
- [ ] Add `role="button"`, `aria-expanded`, `aria-controls` to blade headers
- [ ] Add keyboard event handlers
- [ ] Add `scope="col"` to all table headers
- [ ] Add icons + text to status badges
- [ ] Test with screen reader (NVDA/JAWS)

### Phase 2: Security & Performance (3 hours)
- [ ] Generate SRI hashes for CDN scripts
- [ ] Implement lazy-loading with Intersection Observer
- [ ] Move CSS to external file
- [ ] Add error handling for missing chart data

### Phase 3: Features (8 hours)
- [ ] Implement dark mode toggle
- [ ] Add date range picker for trend chart
- [ ] Integrate html2pdf for PDF export
- [ ] Integrate xlsx for Excel export
- [ ] Add download snapshot button

---

## Quick Wins (< 1 hour each)

1. ✅ Add `aria-hidden="true"` to decorative chevrons
2. ✅ Add `crossorigin="anonymous"` to external scripts
3. ✅ Wrap chart initialization in try-catch
4. ✅ Add "No data" message for empty states
5. ✅ Replace color cycle with pre-assigned colors in Python

