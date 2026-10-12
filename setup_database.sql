-- Metal Fitness Arena database bootstrap.
-- If you already use the existing Attendance database, you do not need to run this.
-- The Flask application creates the mfa_* tables automatically.
-- Run this as a MySQL administrator only if the database does not exist.

CREATE DATABASE IF NOT EXISTS Attendance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
