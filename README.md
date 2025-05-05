# Fixed Asset Management System

✅ **Streamlit-based app for secure asset tracking with QR-based access control**  
✅ **Role-based access: Developer, Client, Auditor, QR Viewer**

---

## Features

- 🔐 **Login system (Streamlit session)**
- 🏠 **Home dashboard**
- 📋 **Editable Fixed Asset Register (FAR) for Developer & Client**
- 🕵️ **Audit Trail log (viewable by Developer, Client, Auditor)**
- 📱 **QR Viewer tab → shows asset details after passcode validation**
- 📷 **QR generation → static (encodes dynamic URL + asset ID)**

---

## Database Schema

Tables:

- `assets` → stores asset master
- `audit_log` → logs add/edit/delete
- `users` → user auth (Developer, Client, Auditor)
- `settings` → stores QR viewer passcode

