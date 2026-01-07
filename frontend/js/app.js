/**
 * SorinFlow Divar Scraper - Dashboard JavaScript
 */

const API_BASE = '/api';
let currentPage = 1;
let cityChart = null;
let trendChart = null;
let loginPhoneNumber = '';
let cookieStatus = { is_valid: false, has_cookies: false };
let pendingScrapingAction = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadDashboard();
    loadCities();
    loadCategories();
    checkCookieStatus();
    
    // Setup form handlers
    document.getElementById('scraper-form').addEventListener('submit', startScraping);
    document.getElementById('proxy-form').addEventListener('submit', addProxy);
    
    // Auto-refresh
    setInterval(loadDashboard, 60000);
    setInterval(checkCookieStatus, 300000);
});

// Section Navigation
function showSection(sectionName) {
    document.querySelectorAll('.section-content').forEach(el => {
        el.style.display = 'none';
    });
    document.getElementById(`section-${sectionName}`).style.display = 'block';
    
    document.querySelectorAll('.nav-link').forEach(el => {
        el.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Load section data
    switch (sectionName) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'properties':
            loadProperties();
            break;
        case 'scraper':
            loadJobs();
            break;
        case 'auth':
            checkAuthStatus();
            loadCookies();
            break;
        case 'proxies':
            loadProxies();
            break;
    }
}

// Toast Notification
function showToast(title, message, type = 'info') {
    const toast = document.getElementById('toast');
    const toastTitle = document.getElementById('toast-title');
    const toastMessage = document.getElementById('toast-message');
    
    toastTitle.textContent = title;
    toastMessage.textContent = message;
    
    toast.className = `toast bg-${type} text-white`;
    
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
}

// Format Numbers (Persian)
function formatNumber(num) {
    if (!num) return '---';
    return new Intl.NumberFormat('fa-IR').format(num);
}

// Format Price
function formatPrice(price) {
    if (!price) return '---';
    if (price >= 1000000000) {
        return formatNumber(Math.round(price / 1000000000)) + ' میلیارد';
    } else if (price >= 1000000) {
        return formatNumber(Math.round(price / 1000000)) + ' میلیون';
    }
    return formatNumber(price) + ' تومان';
}

// API Helper
async function apiCall(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Request failed');
        }
        
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// ==================== Dashboard ====================

async function loadDashboard() {
    try {
        const [stats, health] = await Promise.all([
            apiCall('/stats/dashboard'),
            apiCall('/stats/health')
        ]);
        
        // Update stats
        document.getElementById('stat-total-properties').textContent = formatNumber(stats.total_properties);
        document.getElementById('stat-with-phone').textContent = formatNumber(stats.properties_with_phone);
        document.getElementById('stat-today').textContent = formatNumber(stats.properties_today);
        document.getElementById('stat-active-jobs').textContent = formatNumber(stats.active_jobs);
        
        // Update health
        updateHealthStatus('health-db', health.database);
        updateHealthStatus('health-redis', health.redis);
        updateHealthStatus('health-scraper', health.scraper);
        updateHealthStatus('health-cookie', health.cookie_status);
        
        // Update charts
        updateCityChart(stats.city_distribution);
        updateTrendChart(stats.daily_scraping);
        
    } catch (error) {
        showToast('خطا', 'بارگیری داشبورد ناموفق بود', 'danger');
    }
}

function updateHealthStatus(elementId, status) {
    const element = document.getElementById(elementId);
    let badgeClass = 'bg-success';
    let text = status;
    
    if (status.includes('unhealthy') || status.includes('expired') || status === 'no session') {
        badgeClass = 'bg-danger';
    } else if (status.includes('degraded') || status.includes('unavailable')) {
        badgeClass = 'bg-warning';
    }
    
    element.className = `badge ${badgeClass}`;
    element.textContent = text;
}

function updateCityChart(data) {
    const ctx = document.getElementById('cityChart').getContext('2d');
    
    if (cityChart) {
        cityChart.destroy();
    }
    
    cityChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: data.map(d => d.city),
            datasets: [{
                data: data.map(d => d.count),
                backgroundColor: [
                    '#0d6efd', '#198754', '#dc3545', '#ffc107', '#0dcaf0',
                    '#6f42c1', '#d63384', '#fd7e14', '#20c997', '#6c757d'
                ]
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'right'
                }
            }
        }
    });
}

function updateTrendChart(data) {
    const ctx = document.getElementById('trendChart').getContext('2d');
    
    if (trendChart) {
        trendChart.destroy();
    }
    
    trendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.date),
            datasets: [{
                label: 'تعداد اسکرپ',
                data: data.map(d => d.count),
                borderColor: '#0d6efd',
                backgroundColor: 'rgba(13, 110, 253, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

// ==================== Properties ====================

async function loadProperties() {
    const search = document.getElementById('search-properties').value;
    const city = document.getElementById('filter-city').value;
    const type = document.getElementById('filter-type').value;
    
    try {
        let url = `/properties?page=${currentPage}&size=20`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        if (city) url += `&city=${encodeURIComponent(city)}`;
        if (type) url += `&listing_type=${type}`;
        
        const data = await apiCall(url);
        
        const tbody = document.getElementById('properties-table');
        tbody.innerHTML = '';
        
        if (data.items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="text-center text-muted py-4">
                        <i class="bi bi-inbox" style="font-size: 2rem;"></i>
                        <p class="mt-2">هیچ ملکی یافت نشد</p>
                    </td>
                </tr>
            `;
            return;
        }
        
        data.items.forEach(property => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><code>${property.tag_number}</code></td>
                <td title="${property.title}">${property.title.substring(0, 40)}...</td>
                <td>${property.city_name || '---'}</td>
                <td>${formatNumber(property.area)} متر</td>
                <td>${property.rooms || '---'}</td>
                <td>${formatPrice(property.total_price || property.rent_price)}</td>
                <td>
                    ${property.phone_number 
                        ? `<a href="tel:${property.phone_number}" class="text-success">${property.phone_number}</a>`
                        : '<span class="text-muted">---</span>'
                    }
                </td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="viewProperty(${property.id})">
                        <i class="bi bi-eye"></i>
                    </button>
                    <a href="${property.url}" target="_blank" class="btn btn-sm btn-outline-secondary">
                        <i class="bi bi-box-arrow-up-left"></i>
                    </a>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteProperty(${property.id})">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
        
        // Update pagination
        updatePagination(data.page, data.pages);
        
    } catch (error) {
        showToast('خطا', 'بارگیری لیست املاک ناموفق بود', 'danger');
    }
}

function updatePagination(current, total) {
    const pagination = document.getElementById('properties-pagination');
    pagination.innerHTML = '';
    
    for (let i = 1; i <= total; i++) {
        const li = document.createElement('li');
        li.className = `page-item ${i === current ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#" onclick="goToPage(${i})">${formatNumber(i)}</a>`;
        pagination.appendChild(li);
    }
}

function goToPage(page) {
    currentPage = page;
    loadProperties();
}

async function viewProperty(id) {
    try {
        const property = await apiCall(`/properties/${id}`);
        
        const modal = document.getElementById('property-detail');
        modal.innerHTML = `
            <div class="property-detail">
                ${property.images && property.images.length > 0 ? `
                    <div class="images">
                        ${property.images.map(img => `<img src="${img}" alt="تصویر ملک">`).join('')}
                    </div>
                ` : ''}
                
                <h5>${property.title}</h5>
                <p class="text-muted">${property.description || 'بدون توضیحات'}</p>
                
                <div class="info-grid">
                    <div class="info-item">
                        <label>شناسه</label>
                        <span>${property.tag_number}</span>
                    </div>
                    <div class="info-item">
                        <label>شهر</label>
                        <span>${property.city_name || '---'}</span>
                    </div>
                    <div class="info-item">
                        <label>منطقه</label>
                        <span>${property.district || '---'}</span>
                    </div>
                    <div class="info-item">
                        <label>متراژ</label>
                        <span>${formatNumber(property.area)} متر</span>
                    </div>
                    <div class="info-item">
                        <label>تعداد اتاق</label>
                        <span>${property.rooms || '---'}</span>
                    </div>
                    <div class="info-item">
                        <label>سال ساخت</label>
                        <span>${property.year_built || '---'}</span>
                    </div>
                    <div class="info-item">
                        <label>قیمت کل</label>
                        <span>${formatPrice(property.total_price)}</span>
                    </div>
                    <div class="info-item">
                        <label>اجاره/ودیعه</label>
                        <span>${formatPrice(property.rent_price)} / ${formatPrice(property.deposit)}</span>
                    </div>
                    <div class="info-item">
                        <label>شماره تماس</label>
                        <span>${property.phone_number 
                            ? `<a href="tel:${property.phone_number}">${property.phone_number}</a>` 
                            : '---'}</span>
                    </div>
                </div>
                
                <div class="mt-3">
                    <label>امکانات:</label>
                    <div class="d-flex flex-wrap gap-1 mt-1">
                        ${property.has_elevator ? '<span class="badge bg-primary">آسانسور</span>' : ''}
                        ${property.has_parking ? '<span class="badge bg-primary">پارکینگ</span>' : ''}
                        ${property.has_storage ? '<span class="badge bg-primary">انباری</span>' : ''}
                        ${property.has_balcony ? '<span class="badge bg-primary">بالکن</span>' : ''}
                    </div>
                </div>
                
                <div class="mt-3">
                    <a href="${property.url}" target="_blank" class="btn btn-primary">
                        <i class="bi bi-box-arrow-up-left"></i> مشاهده در دیوار
                    </a>
                </div>
            </div>
        `;
        
        const modalElement = new bootstrap.Modal(document.getElementById('propertyModal'));
        modalElement.show();
        
    } catch (error) {
        showToast('خطا', 'بارگیری جزئیات ملک ناموفق بود', 'danger');
    }
}

async function deleteProperty(id) {
    if (!confirm('آیا از حذف این ملک اطمینان دارید؟')) return;
    
    try {
        await apiCall(`/properties/${id}`, { method: 'DELETE' });
        showToast('موفق', 'ملک با موفقیت حذف شد', 'success');
        loadProperties();
    } catch (error) {
        showToast('خطا', 'حذف ملک ناموفق بود', 'danger');
    }
}

async function exportProperties() {
    try {
        const city = document.getElementById('filter-city').value;
        const type = document.getElementById('filter-type').value;
        
        const data = await apiCall('/properties/export', {
            method: 'POST',
            body: JSON.stringify({ city, listing_type: type })
        });
        
        // Download as JSON
        const blob = new Blob([JSON.stringify(data.data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'properties-export.json';
        a.click();
        
        showToast('موفق', 'فایل دانلود شد', 'success');
    } catch (error) {
        showToast('خطا', 'خروجی گرفتن ناموفق بود', 'danger');
    }
}

// ==================== Scraper ====================

async function loadCities() {
    try {
        const cities = await apiCall('/scraper/cities');
        
        const scraperCity = document.getElementById('scraper-city');
        const filterCity = document.getElementById('filter-city');
        
        cities.forEach(city => {
            scraperCity.innerHTML += `<option value="${city.slug}">${city.name}</option>`;
            filterCity.innerHTML += `<option value="${city.name}">${city.name}</option>`;
        });
    } catch (error) {
        console.error('Failed to load cities:', error);
    }
}

async function loadCategories() {
    try {
        const categories = await apiCall('/scraper/categories');
        
        const select = document.getElementById('scraper-category');
        categories.forEach(cat => {
            select.innerHTML += `<option value="${cat.slug}">${cat.name}</option>`;
        });
    } catch (error) {
        console.error('Failed to load categories:', error);
    }
}

async function startScraping(e) {
    e.preventDefault();
    
    const city = document.getElementById('scraper-city').value;
    const category = document.getElementById('scraper-category').value;
    const maxPages = parseInt(document.getElementById('scraper-pages').value);
    const downloadImages = document.getElementById('scraper-images').checked;
    
    // Check cookie status before scraping
    if (!cookieStatus.is_valid) {
        pendingScrapingAction = { type: 'bulk', city, category, maxPages, downloadImages };
        showCookieWarning();
        return;
    }
    
    await executeBulkScraping(city, category, maxPages, downloadImages);
}

async function executeBulkScraping(city, category, maxPages, downloadImages) {
    try {
        const result = await apiCall('/scraper/start', {
            method: 'POST',
            body: JSON.stringify({
                city,
                category,
                max_pages: maxPages,
                download_images: downloadImages
            })
        });
        
        showToast('موفق', `اسکرپینگ شروع شد: ${result.job_id}`, 'success');
        loadJobs();
        
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

async function loadJobs() {
    try {
        const data = await apiCall('/scraper/jobs?limit=20');
        
        const tbody = document.getElementById('jobs-table');
        tbody.innerHTML = '';
        
        if (data.items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center text-muted py-4">
                        هیچ تسکی وجود ندارد
                    </td>
                </tr>
            `;
            return;
        }
        
        data.items.forEach(job => {
            const row = document.createElement('tr');
            const statusClass = `status-${job.status}`;
            
            row.innerHTML = `
                <td><code>${job.job_id.substring(0, 8)}...</code></td>
                <td><span class="badge ${statusClass}">${job.status}</span></td>
                <td>
                    <div class="progress" style="width: 100px;">
                        <div class="progress-bar" role="progressbar" 
                             style="width: ${job.progress}%">${Math.round(job.progress)}%</div>
                    </div>
                </td>
                <td>${job.new_items} / ${job.updated_items}</td>
                <td>${job.started_at ? new Date(job.started_at).toLocaleString('fa-IR') : '---'}</td>
                <td>
                    ${job.status === 'running' ? `
                        <button class="btn btn-sm btn-outline-danger" onclick="cancelJob('${job.job_id}')">
                            <i class="bi bi-stop-fill"></i>
                        </button>
                    ` : ''}
                </td>
            `;
            tbody.appendChild(row);
        });
        
    } catch (error) {
        showToast('خطا', 'بارگیری تسک‌ها ناموفق بود', 'danger');
    }
}

async function cancelJob(jobId) {
    if (!confirm('آیا از لغو این تسک اطمینان دارید؟')) return;
    
    try {
        await apiCall(`/scraper/jobs/${jobId}/cancel`, { method: 'POST' });
        showToast('موفق', 'تسک لغو شد', 'success');
        loadJobs();
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

async function scrapeSingle() {
    const url = document.getElementById('single-url').value;
    
    if (!url || !url.includes('divar.ir/v/')) {
        showToast('خطا', 'لطفاً یک آدرس معتبر دیوار وارد کنید', 'warning');
        return;
    }
    
    // Check cookie status before scraping
    if (!cookieStatus.is_valid) {
        pendingScrapingAction = { type: 'single', url };
        showCookieWarning();
        return;
    }
    
    await executeSingleScraping(url);
}

async function executeSingleScraping(url) {
    try {
        const result = await apiCall('/scraper/scrape-single', {
            method: 'POST',
            body: JSON.stringify({ url })
        });
        
        if (result.success) {
            showToast('موفق', 'ملک با موفقیت اسکرپ شد', 'success');
        } else {
            showToast('خطا', result.message, 'danger');
        }
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

// Cookie Warning Modal Functions
function showCookieWarning() {
    const message = document.getElementById('cookie-warning-message');
    if (cookieStatus.has_cookies) {
        message.textContent = 'نشست شما منقضی شده است. لطفاً دوباره وارد شوید.';
    } else {
        message.textContent = 'شما هنوز وارد حساب دیوار نشده‌اید.';
    }
    
    const modal = new bootstrap.Modal(document.getElementById('cookieWarningModal'));
    modal.show();
    
    // Setup continue button handler
    document.getElementById('continue-scraping-btn').onclick = function() {
        modal.hide();
        continueScraping();
    };
}

function continueScraping() {
    if (!pendingScrapingAction) return;
    
    if (pendingScrapingAction.type === 'bulk') {
        const { city, category, maxPages, downloadImages } = pendingScrapingAction;
        executeBulkScraping(city, category, maxPages, downloadImages);
    } else if (pendingScrapingAction.type === 'single') {
        executeSingleScraping(pendingScrapingAction.url);
    }
    
    pendingScrapingAction = null;
}

function goToAuthSection() {
    // Close modal first
    const modal = bootstrap.Modal.getInstance(document.getElementById('cookieWarningModal'));
    if (modal) modal.hide();
    
    // Navigate to auth section
    document.querySelectorAll('.section-content').forEach(el => {
        el.style.display = 'none';
    });
    document.getElementById('section-auth').style.display = 'block';
    
    document.querySelectorAll('.nav-link').forEach(el => {
        el.classList.remove('active');
    });
    
    checkAuthStatus();
    loadCookies();
}

// ==================== Authentication ====================

async function checkCookieStatus() {
    try {
        const status = await apiCall('/auth/status');
        cookieStatus = status; // Store globally
        
        const badge = document.getElementById('cookie-status');
        if (status.is_valid) {
            badge.className = 'badge bg-success';
            badge.innerHTML = '<i class="bi bi-circle-fill"></i> متصل';
        } else if (status.has_cookies) {
            badge.className = 'badge bg-warning';
            badge.innerHTML = '<i class="bi bi-circle-fill"></i> منقضی';
        } else {
            badge.className = 'badge bg-danger';
            badge.innerHTML = '<i class="bi bi-circle-fill"></i> نیاز به ورود';
        }
    } catch (error) {
        console.error('Failed to check cookie status:', error);
    }
}

async function checkAuthStatus() {
    try {
        const status = await apiCall('/auth/status');
        
        const statusDiv = document.getElementById('auth-status');
        
        if (status.is_valid) {
            statusDiv.className = 'alert alert-success';
            statusDiv.innerHTML = `
                <i class="bi bi-check-circle"></i>
                <strong>وضعیت: متصل</strong><br>
                شماره: ${status.phone_number}<br>
                انقضا: ${status.expires_at || 'نامشخص'}
            `;
        } else if (status.has_cookies) {
            statusDiv.className = 'alert alert-warning';
            statusDiv.innerHTML = `
                <i class="bi bi-exclamation-triangle"></i>
                <strong>وضعیت: منقضی شده</strong><br>
                ${status.message}
            `;
        } else {
            statusDiv.className = 'alert alert-info';
            statusDiv.innerHTML = `
                <i class="bi bi-info-circle"></i>
                ${status.message}
            `;
        }
    } catch (error) {
        console.error('Failed to check auth status:', error);
    }
}

async function initiateLogin() {
    const phone = document.getElementById('auth-phone').value;
    
    if (!phone || !/^09\d{9}$/.test(phone)) {
        showToast('خطا', 'لطفاً شماره موبایل معتبر وارد کنید', 'warning');
        return;
    }
    
    try {
        const result = await apiCall('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ phone_number: phone })
        });
        
        if (result.requires_code) {
            loginPhoneNumber = phone;
            document.getElementById('auth-login-form').style.display = 'none';
            document.getElementById('auth-verify-form').style.display = 'block';
            showToast('موفق', 'کد تأیید ارسال شد', 'success');
        } else {
            showToast('خطا', result.message, 'danger');
        }
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

async function verifyCode() {
    const code = document.getElementById('auth-code').value;
    
    if (!code || code.length !== 6) {
        showToast('خطا', 'لطفاً کد ۶ رقمی را وارد کنید', 'warning');
        return;
    }
    
    try {
        const result = await apiCall(`/auth/verify?phone_number=${loginPhoneNumber}`, {
            method: 'POST',
            body: JSON.stringify({ code })
        });
        
        if (result.success) {
            showToast('موفق', 'ورود موفقیت‌آمیز بود', 'success');
            document.getElementById('auth-login-form').style.display = 'block';
            document.getElementById('auth-verify-form').style.display = 'none';
            checkAuthStatus();
            checkCookieStatus();
        } else {
            showToast('خطا', result.message, 'danger');
        }
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

async function refreshSession() {
    try {
        const result = await apiCall('/auth/refresh', { method: 'POST' });
        
        if (result.success) {
            showToast('موفق', result.message, 'success');
        } else {
            showToast('هشدار', result.message, 'warning');
        }
        
        checkAuthStatus();
        checkCookieStatus();
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

async function logout() {
    if (!confirm('آیا از خروج اطمینان دارید؟')) return;
    
    try {
        await apiCall('/auth/logout', { method: 'POST' });
        showToast('موفق', 'خروج موفقیت‌آمیز بود', 'success');
        checkAuthStatus();
        checkCookieStatus();
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

async function loadCookies() {
    try {
        const data = await apiCall('/auth/cookies');
        
        const container = document.getElementById('cookies-list');
        
        if (data.cookies.length === 0) {
            container.innerHTML = '<p class="text-muted text-center">هیچ نشستی ذخیره نشده</p>';
            return;
        }
        
        container.innerHTML = data.cookies.map(cookie => `
            <div class="d-flex justify-content-between align-items-center p-2 border-bottom">
                <div>
                    <strong>${cookie.phone_number}</strong>
                    <br>
                    <small class="text-muted">${cookie.is_valid ? 'معتبر' : 'منقضی'}</small>
                </div>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteCookie(${cookie.id})">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Failed to load cookies:', error);
    }
}

async function deleteCookie(id) {
    if (!confirm('آیا از حذف این نشست اطمینان دارید؟')) return;
    
    try {
        await apiCall(`/auth/cookies/${id}`, { method: 'DELETE' });
        showToast('موفق', 'نشست حذف شد', 'success');
        loadCookies();
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

// ==================== Proxies ====================

async function loadProxies() {
    try {
        const data = await apiCall('/proxies');
        
        const tbody = document.getElementById('proxies-table');
        tbody.innerHTML = '';
        
        if (data.items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center text-muted py-4">
                        هیچ پراکسی‌ای وجود ندارد
                    </td>
                </tr>
            `;
            return;
        }
        
        data.items.forEach(proxy => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${proxy.address}</td>
                <td>${proxy.port}</td>
                <td>
                    <span class="badge ${proxy.is_working ? 'bg-success' : 'bg-danger'}">
                        ${proxy.is_working ? 'فعال' : 'غیرفعال'}
                    </span>
                </td>
                <td>${proxy.success_count} / ${proxy.fail_count}</td>
                <td>${proxy.avg_response_time ? proxy.avg_response_time.toFixed(2) + 's' : '---'}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="testProxy(${proxy.id})">
                        <i class="bi bi-speedometer2"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-warning" onclick="toggleProxy(${proxy.id})">
                        <i class="bi bi-toggle-on"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteProxy(${proxy.id})">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
        
    } catch (error) {
        showToast('خطا', 'بارگیری پراکسی‌ها ناموفق بود', 'danger');
    }
}

async function addProxy(e) {
    e.preventDefault();
    
    const address = document.getElementById('proxy-address').value;
    const port = parseInt(document.getElementById('proxy-port').value);
    const protocol = document.getElementById('proxy-protocol').value;
    const username = document.getElementById('proxy-username').value;
    const password = document.getElementById('proxy-password').value;
    
    try {
        await apiCall('/proxies', {
            method: 'POST',
            body: JSON.stringify({ address, port, protocol, username, password })
        });
        
        showToast('موفق', 'پراکسی اضافه شد', 'success');
        e.target.reset();
        loadProxies();
        
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

async function testProxy(id) {
    try {
        showToast('در حال تست', 'لطفاً صبر کنید...', 'info');
        const result = await apiCall(`/proxies/${id}/test`, { method: 'POST' });
        
        if (result.success) {
            showToast('موفق', `زمان پاسخ: ${result.response_time.toFixed(2)}s`, 'success');
        } else {
            showToast('ناموفق', result.error || 'پراکسی کار نمی‌کند', 'danger');
        }
        
        loadProxies();
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

async function toggleProxy(id) {
    try {
        const result = await apiCall(`/proxies/${id}/toggle`, { method: 'POST' });
        showToast('موفق', result.message, 'success');
        loadProxies();
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

async function deleteProxy(id) {
    if (!confirm('آیا از حذف این پراکسی اطمینان دارید؟')) return;
    
    try {
        await apiCall(`/proxies/${id}`, { method: 'DELETE' });
        showToast('موفق', 'پراکسی حذف شد', 'success');
        loadProxies();
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

async function testAllProxies() {
    try {
        showToast('در حال تست', 'تست همه پراکسی‌ها شروع شد...', 'info');
        const result = await apiCall('/proxies/test-all', { method: 'POST' });
        showToast('موفق', `${result.working} از ${result.total} پراکسی فعال`, 'success');
        loadProxies();
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}

async function importProxies() {
    const proxyList = document.getElementById('proxy-import').value;
    
    if (!proxyList.trim()) {
        showToast('خطا', 'لطفاً لیست پراکسی‌ها را وارد کنید', 'warning');
        return;
    }
    
    try {
        const result = await apiCall('/proxies/import', {
            method: 'POST',
            body: JSON.stringify({ proxy_list: proxyList })
        });
        
        showToast('موفق', result.message, 'success');
        document.getElementById('proxy-import').value = '';
        loadProxies();
        
    } catch (error) {
        showToast('خطا', error.message, 'danger');
    }
}
