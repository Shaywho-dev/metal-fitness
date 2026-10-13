-- Metal Fitness Arena database bootstrap.
-- This creates the database used by the Flask application.
-- Database name is intentionally uppercase to match the app default config.

CREATE DATABASE IF NOT EXISTS `MFA_GYM_REPORT` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'MFA_User'@'localhost' IDENTIFIED BY 'change_me';
GRANT ALL PRIVILEGES ON `MFA_GYM_REPORT`.* TO 'MFA_User'@'localhost';
GRANT ALL PRIVILEGES ON `MFA_GYM_REPORT`.* TO 'MFA_User'@'%';
FLUSH PRIVILEGES;
