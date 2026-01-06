# SorinFlow Divar Scraper

اسکرپر حرفه‌ای دیوار با قابلیت استخراج کامل اطلاعات ملک، شماره تماس و تصاویر

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green)
![Playwright](https://img.shields.io/badge/Playwright-Stealth-orange)
![Docker](https://img.shields.io/badge/Docker-Compose-blue)

## ویژگی‌ها

- 🔒 **احراز هویت با OTP**: ورود به دیوار با شماره تلفن و کد یکبار مصرف
- 🍪 **مدیریت کوکی**: ذخیره و بازیابی خودکار کوکی‌ها با اخطار انقضا
- 🛡️ **Anti-Detection**: ماژول Stealth پیشرفته برای جلوگیری از شناسایی
- 📱 **استخراج شماره تماس**: دریافت شماره تلفن آگهی‌دهندگان
- 📸 **دانلود تصاویر**: ذخیره خودکار تصاویر ملک
- 🏠 **اطلاعات کامل ملک**: متراژ، قیمت، آدرس، امکانات و...
- 📊 **داشبورد مدیریت**: رابط کاربری RTL فارسی
- 🔄 **Proxy Support**: پشتیبانی از پروکسی با rotation
- 📈 **آمار و گزارشات**: نمودار و آمار کامل اسکرپ

## پیش‌نیازها

- Docker & Docker Compose
- حداقل 2GB RAM
- 20GB فضای ذخیره‌سازی

## نصب سریع

```bash
# کلون پروژه
git clone https://github.com/your-repo/sorinflow-divar-scraper.git
cd sorinflow-divar-scraper

# ایجاد فایل تنظیمات
cp .env.example .env

# راه‌اندازی
chmod +x start.sh
./start.sh
```

## تنظیمات (.env)

```env
# Database
POSTGRES_USER=sorinflow
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=divar_scraper

# Redis
REDIS_PASSWORD=your_redis_password

# API
SECRET_KEY=your_secret_key
API_HOST=0.0.0.0
API_PORT=8000

# Scraper
HEADLESS=true
RATE_LIMIT_PER_MINUTE=20
```

## API Endpoints

### احراز هویت
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | درخواست ارسال کد OTP |
| POST | `/api/auth/verify` | تأیید کد و ورود |
| GET | `/api/auth/status` | وضعیت لاگین |
| GET | `/api/auth/cookies` | لیست کوکی‌ها |
| DELETE | `/api/auth/cookies/{id}` | حذف کوکی |

### اسکرپر
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/scraper/start` | شروع اسکرپ |
| POST | `/api/scraper/stop/{job_id}` | توقف اسکرپ |
| GET | `/api/scraper/jobs` | لیست job ها |
| GET | `/api/scraper/jobs/{job_id}` | جزئیات job |
| GET | `/api/scraper/logs/{job_id}` | لاگ‌های job |

### ملک‌ها
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/properties` | لیست ملک‌ها |
| GET | `/api/properties/{id}` | جزئیات ملک |
| GET | `/api/properties/{id}/images` | تصاویر ملک |
| DELETE | `/api/properties/{id}` | حذف ملک |
| GET | `/api/properties/export` | خروجی CSV/JSON |

### آمار
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stats` | آمار کلی |
| GET | `/api/stats/daily` | آمار روزانه |
| GET | `/api/stats/cities` | آمار به تفکیک شهر |

### پروکسی
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/proxies` | لیست پروکسی‌ها |
| POST | `/api/proxies` | افزودن پروکسی |
| PUT | `/api/proxies/{id}` | ویرایش پروکسی |
| DELETE | `/api/proxies/{id}` | حذف پروکسی |
| POST | `/api/proxies/{id}/test` | تست پروکسی |

## شهرهای پشتیبانی شده

تهران، کرج، شیراز، اصفهان، تبریز، مشهد، اهواز، قم، کرمانشاه، ارومیه، رشت، زاهدان، کرمان، همدان، یزد، اردبیل، بندرعباس، ساری، قزوین، زنجان

## دسته‌بندی‌ها

- خرید آپارتمان
- فروش آپارتمان
- اجاره آپارتمان
- خرید ویلا
- فروش ویلا
- اجاره ویلا
- خرید زمین
- فروش زمین
- و سایر دسته‌ها...

## ساختار پروژه

```
sorinflow-divar-scraper/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── auth.py
│   │       ├── properties.py
│   │       ├── proxies.py
│   │       ├── scraper.py
│   │       └── stats.py
│   ├── models/
│   │   ├── property.py
│   │   ├── cookie.py
│   │   ├── proxy.py
│   │   └── scraping_job.py
│   ├── scraper/
│   │   ├── auth.py
│   │   ├── divar_scraper.py
│   │   └── stealth.py
│   ├── config.py
│   ├── database.py
│   └── main.py
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── nginx/
│   └── nginx.conf
├── data/
│   ├── images/
│   └── cookies/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── init.sql
```

## دستورات مفید

```bash
# مشاهده لاگ‌ها
docker compose logs -f backend

# ری‌استارت سرویس‌ها
docker compose restart

# توقف سرویس‌ها
docker compose down

# پاک کردن کامل (با داده‌ها)
docker compose down -v

# ورود به کانتینر
docker compose exec backend bash

# اتصال به دیتابیس
docker compose exec db psql -U sorinflow -d divar_scraper
```

## عیب‌یابی

### مشکل اتصال به دیتابیس
```bash
docker compose logs db
docker compose restart db
```

### مشکل Playwright
```bash
docker compose exec backend playwright install chromium
```

### کوکی منقضی شده
از داشبورد مجدداً لاگین کنید یا:
```bash
curl -X POST http://localhost:8000/api/auth/login -d '{"phone": "09123456789"}'
```

## امنیت

- از رمز عبور قوی برای دیتابیس استفاده کنید
- SECRET_KEY را تغییر دهید
- در محیط production از HTTPS استفاده کنید
- Rate limit را بررسی و تنظیم کنید

## لایسنس

MIT License - استفاده آزاد با ذکر منبع

## پشتیبانی

برای گزارش مشکل یا پیشنهاد، Issue ایجاد کنید.

---

ساخته شده با ❤️ توسط SorinFlow
