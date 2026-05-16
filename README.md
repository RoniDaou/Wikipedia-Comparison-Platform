# 🌍 Wikipedia Country Infobox Scraper

A full-stack web application for scraping, storing, and comparing semi-structured data from Wikipedia country infoboxes. This project focuses on collecting data from all 193 UN-recognized countries.

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Running the Application](#running-the-application)
- [Usage Guide](#usage-guide)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Technical Details](#technical-details)

---

## 🎯 Overview

This tool implements a complete data pipeline for collecting, storing, comparing, and analyzing semi-structured data from Wikipedia country infoboxes. The system provides:

1. **Data Collection**: Automated web scraping of Wikipedia infoboxes
2. **Data Storage**: MongoDB NoSQL database for flexible schema storage
3. **Data Comparison**: Advanced algorithms for comparing country data
4. **Web Interface**: Modern, responsive frontend for data visualization

The project focuses on UN-recognized countries (193 member states) and features intelligent duplicate detection, data normalization, and real-time progress tracking.

---

## ✨ Features

### Data Collection
- ✅ **Single Country Scraping** with duplicate detection
- ✅ **Bulk Scraping** with three modes:
  - ♻️ Re-scrape all countries (update existing data)
  - ✅ Scrape new countries only (skip existing)
  - ❌ Cancel operation
- ✅ **Live Progress Panel** with pause/resume/stop controls
- ✅ **Smart Rate Limiting** to respect Wikipedia servers
- ✅ **Unicode Normalization** for consistent naming
- ✅ **Case-Insensitive Storage** to prevent duplicates

### Data Browsing
- ✅ **Pagination**: View 10/20/30/50/100 countries per page
- ✅ **Search Functionality** for quick country lookup
- ✅ **Detailed Modal View** showing all infobox fields
- ✅ **Responsive Grid Layout** for all screen sizes
- ✅ **Sorted Display** with country count

### Data Comparison
- ✅ **Side-by-Side Comparison** of any two countries
- ✅ **Similarity Score** calculation
- ✅ **Detailed Diff Reports** showing common/unique fields
- ✅ **Field-Level Analysis** with difference highlighting
- ✅ **Comparison History** stored in database

### User Interface
- ✅ **Modern Design** with UN blue theme
- ✅ **Custom Modals** (no browser dialogs)
- ✅ **Real-Time Statistics** dashboard
- ✅ **Mobile Responsive** design
- ✅ **Smooth Animations** and transitions

## 🚀 Installation

### Step 1: Install MongoDB

#### Windows
1. Download MongoDB from: https://www.mongodb.com/try/download/community
2. Run the installer (.msi file)
3. Choose "Complete" installation
4. Check "Install MongoDB as a Service"
5. Keep default data directory: `C:\Program Files\MongoDB\Server\6.0\data`
6. Complete installation

**Verify installation:**
```cmd
mongosh