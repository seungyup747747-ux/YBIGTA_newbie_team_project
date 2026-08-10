CREATE DATABASE IF NOT EXISTS weather_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE weather_db;

CREATE TABLE IF NOT EXISTS weather_observations (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    location VARCHAR(50) NOT NULL,
    latitude DECIMAL(9, 6) NOT NULL,
    longitude DECIMAL(9, 6) NOT NULL,
    observed_at DATETIME NOT NULL,
    temperature DECIMAL(5, 2) NOT NULL,
    apparent_temperature DECIMAL(5, 2) NOT NULL,
    relative_humidity TINYINT UNSIGNED NOT NULL,
    precipitation DECIMAL(7, 2) NOT NULL,
    wind_speed DECIMAL(6, 2) NOT NULL,
    weather_code SMALLINT UNSIGNED NOT NULL,
    risk_score TINYINT UNSIGNED NOT NULL,
    risk_level ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL') NOT NULL,
    risk_reasons JSON NOT NULL,
    collected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    CONSTRAINT uq_weather_location_observed
        UNIQUE (location, observed_at),

    CONSTRAINT chk_weather_latitude
        CHECK (latitude BETWEEN -90 AND 90),

    CONSTRAINT chk_weather_longitude
        CHECK (longitude BETWEEN -180 AND 180),

    CONSTRAINT chk_weather_humidity
        CHECK (relative_humidity BETWEEN 0 AND 100),

    CONSTRAINT chk_weather_precipitation
        CHECK (precipitation >= 0),

    CONSTRAINT chk_weather_wind_speed
        CHECK (wind_speed >= 0),

    CONSTRAINT chk_weather_code
        CHECK (weather_code BETWEEN 0 AND 99),

    CONSTRAINT chk_weather_risk_score
        CHECK (risk_score BETWEEN 0 AND 100),

    INDEX idx_weather_observed_at (observed_at),
    INDEX idx_weather_location_time (location, observed_at),
    INDEX idx_weather_risk_time (risk_level, observed_at)
) ENGINE=InnoDB;
