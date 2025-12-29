<?php
/**
 * Noisy Pi - JSON API
 * 
 * Endpoints:
 *   GET  /api.php?action=measurements&start=TIMESTAMP&end=TIMESTAMP
 *   GET  /api.php?action=measurement&id=ID
 *   GET  /api.php?action=spectrogram&start=TIMESTAMP&end=TIMESTAMP
 *   GET  /api.php?action=stats&start=TIMESTAMP&end=TIMESTAMP
 *   GET  /api.php?action=hourly&start=TIMESTAMP&end=TIMESTAMP
 *   GET  /api.php?action=anomalies&threshold=2.0&limit=100
 *   POST /api.php?action=annotate (body: {id, annotation})
 *   GET  /api.php?action=latest&count=10
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

// Handle preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    exit(0);
}

// Configuration
define('DATA_DIR', getenv('NOISY_PI_DATA') ?: '/var/lib/noisy-pi');
define('DB_PATH', DATA_DIR . '/noisy.db');

// Development fallback
$db_path = DB_PATH;
if (!file_exists($db_path)) {
    $dev_path = __DIR__ . '/../data/noisy.db';
    if (file_exists($dev_path)) {
        $db_path = $dev_path;
    }
}

/**
 * Get database connection
 */
function getDB() {
    global $db_path;
    
    if (!file_exists($db_path)) {
        jsonError('Database not found', 500);
    }
    
    try {
        $db = new PDO('sqlite:' . $db_path);
        $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $db->exec('PRAGMA journal_mode=WAL');
        return $db;
    } catch (PDOException $e) {
        jsonError('Database connection failed: ' . $e->getMessage(), 500);
    }
}

/**
 * Send JSON response
 */
function jsonResponse($data) {
    echo json_encode($data, JSON_NUMERIC_CHECK);
    exit;
}

/**
 * Send JSON error
 */
function jsonError($message, $code = 400) {
    http_response_code($code);
    echo json_encode(['error' => $message]);
    exit;
}

/**
 * Get request parameter
 */
function getParam($name, $default = null) {
    return $_GET[$name] ?? $_POST[$name] ?? $default;
}

/**
 * Decompress spectrogram blob
 */
function decompressSpectrogram($blob) {
    if (empty($blob)) return null;
    $decompressed = @gzuncompress($blob);
    return $decompressed !== false ? $decompressed : $blob;
}

/**
 * Convert spectrogram blob to array of arrays
 */
function spectrogramToArray($blob, $bins = 256, $snapshots = 10) {
    $data = decompressSpectrogram($blob);
    if (!$data || strlen($data) < $bins * $snapshots) {
        return null;
    }
    
    $result = [];
    for ($s = 0; $s < $snapshots; $s++) {
        $spectrum = [];
        for ($b = 0; $b < $bins; $b++) {
            $offset = $s * $bins + $b;
            $value = ord($data[$offset]);
            // Convert back to dB: 0-255 maps to -90 to +10 dB
            $db = -90 + ($value / 255.0) * 100;
            $spectrum[] = round($db, 1);
        }
        $result[] = $spectrum;
    }
    return $result;
}

// Get action
$action = getParam('action', 'measurements');

// Route to handler
switch ($action) {
    case 'measurements':
        getMeasurements();
        break;
    case 'measurement':
        getMeasurement();
        break;
    case 'spectrogram':
        getSpectrogram();
        break;
    case 'stats':
        getStats();
        break;
    case 'hourly':
        getHourlyStats();
        break;
    case 'anomalies':
        getAnomalies();
        break;
    case 'annotate':
        updateAnnotation();
        break;
    case 'latest':
        getLatest();
        break;
    case 'status':
        getStatus();
        break;
    case 'snippets':
        getSnippets();
        break;
    case 'snippet':
        serveSnippet();
        break;
    case 'delete_snippet':
        deleteSnippet();
        break;
    case 'config':
        getConfig();
        break;
    case 'save_config':
        saveConfig();
        break;
    default:
        jsonError('Unknown action: ' . $action);
}

/**
 * GET measurements (without spectrogram data for efficiency)
 */
function getMeasurements() {
    $start = intval(getParam('start', time() - 3600));
    $end = intval(getParam('end', time()));
    
    $db = getDB();
    $stmt = $db->prepare('
        SELECT id, timestamp, laeq, lmax, lmin, l10, l50, l90,
               spectral_centroid, spectral_flatness, dominant_freq,
               event_count, anomaly_score, annotation
        FROM measurements
        WHERE timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp ASC
        LIMIT 10000
    ');
    $stmt->execute([$start, $end]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    jsonResponse([
        'start' => $start,
        'end' => $end,
        'count' => count($rows),
        'data' => $rows
    ]);
}

/**
 * GET single measurement with spectrogram
 */
function getMeasurement() {
    $id = intval(getParam('id', 0));
    if ($id <= 0) {
        jsonError('Invalid measurement ID');
    }
    
    $db = getDB();
    $stmt = $db->prepare('SELECT * FROM measurements WHERE id = ?');
    $stmt->execute([$id]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if (!$row) {
        jsonError('Measurement not found', 404);
    }
    
    // Convert spectrogram
    if (!empty($row['spectrogram'])) {
        $row['spectrogram'] = spectrogramToArray($row['spectrogram']);
    }
    
    jsonResponse($row);
}

/**
 * GET spectrogram data for time range
 */
function getSpectrogram() {
    $start = intval(getParam('start', time() - 3600));
    $end = intval(getParam('end', time()));
    $maxPoints = intval(getParam('max', 200));
    
    $db = getDB();
    
    // Count total points
    $countStmt = $db->prepare('
        SELECT COUNT(*) as cnt FROM measurements
        WHERE timestamp >= ? AND timestamp <= ?
    ');
    $countStmt->execute([$start, $end]);
    $total = $countStmt->fetch(PDO::FETCH_ASSOC)['cnt'];
    
    // Determine sampling interval if too many points
    $skipFactor = max(1, intval(ceil($total / $maxPoints)));
    
    $stmt = $db->prepare('
        SELECT id, timestamp, spectrogram
        FROM measurements
        WHERE timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp ASC
    ');
    $stmt->execute([$start, $end]);
    
    $spectrograms = [];
    $timestamps = [];
    $counter = 0;
    
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        if ($counter % $skipFactor === 0) {
            $timestamps[] = $row['timestamp'];
            $spectrograms[] = spectrogramToArray($row['spectrogram']);
        }
        $counter++;
    }
    
    // Generate frequency labels (Hz)
    $sampleRate = 48000;
    $bins = 256;
    $freqLabels = [];
    for ($i = 0; $i < $bins; $i++) {
        $freqLabels[] = round($i * ($sampleRate / 2) / $bins);
    }
    
    jsonResponse([
        'start' => $start,
        'end' => $end,
        'count' => count($timestamps),
        'total' => $total,
        'skip_factor' => $skipFactor,
        'timestamps' => $timestamps,
        'frequencies' => $freqLabels,
        'snapshots_per_interval' => 10,
        'data' => $spectrograms
    ]);
}

/**
 * GET aggregate statistics
 */
function getStats() {
    $start = intval(getParam('start', time() - 86400));
    $end = intval(getParam('end', time()));
    
    $db = getDB();
    $stmt = $db->prepare('
        SELECT 
            COUNT(*) as count,
            AVG(laeq) as avg_laeq,
            MAX(lmax) as max_level,
            MIN(lmin) as min_level,
            AVG(l50) as avg_l50,
            AVG(spectral_centroid) as avg_centroid,
            AVG(spectral_flatness) as avg_flatness,
            SUM(event_count) as total_events,
            SUM(CASE WHEN anomaly_score > 2.0 THEN 1 ELSE 0 END) as anomaly_count
        FROM measurements
        WHERE timestamp >= ? AND timestamp <= ?
    ');
    $stmt->execute([$start, $end]);
    $stats = $stmt->fetch(PDO::FETCH_ASSOC);
    
    $stats['start'] = $start;
    $stats['end'] = $end;
    $stats['duration_hours'] = ($end - $start) / 3600;
    
    jsonResponse($stats);
}

/**
 * GET hourly aggregated statistics
 */
function getHourlyStats() {
    $start = intval(getParam('start', time() - 86400));
    $end = intval(getParam('end', time()));
    
    $db = getDB();
    $stmt = $db->prepare('
        SELECT 
            (timestamp / 3600) * 3600 as hour_start,
            COUNT(*) as count,
            AVG(laeq) as avg_laeq,
            MAX(lmax) as max_level,
            MIN(lmin) as min_level,
            AVG(l50) as avg_l50,
            AVG(spectral_centroid) as avg_centroid,
            SUM(event_count) as total_events,
            SUM(CASE WHEN anomaly_score > 2.0 THEN 1 ELSE 0 END) as anomaly_count
        FROM measurements
        WHERE timestamp >= ? AND timestamp <= ?
        GROUP BY hour_start
        ORDER BY hour_start ASC
    ');
    $stmt->execute([$start, $end]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    jsonResponse([
        'start' => $start,
        'end' => $end,
        'count' => count($rows),
        'data' => $rows
    ]);
}

/**
 * GET anomalies
 */
function getAnomalies() {
    $threshold = floatval(getParam('threshold', 2.0));
    $limit = intval(getParam('limit', 100));
    $start = getParam('start') ? intval(getParam('start')) : null;
    $end = getParam('end') ? intval(getParam('end')) : null;
    
    $db = getDB();
    
    $query = '
        SELECT id, timestamp, laeq, lmax, anomaly_score, annotation,
               spectral_centroid, dominant_freq, snippet_path
        FROM measurements
        WHERE anomaly_score > ?
    ';
    $params = [$threshold];
    
    if ($start) {
        $query .= ' AND timestamp >= ?';
        $params[] = $start;
    }
    if ($end) {
        $query .= ' AND timestamp <= ?';
        $params[] = $end;
    }
    
    $query .= ' ORDER BY anomaly_score DESC LIMIT ?';
    $params[] = $limit;
    
    $stmt = $db->prepare($query);
    $stmt->execute($params);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    jsonResponse([
        'threshold' => $threshold,
        'count' => count($rows),
        'data' => $rows
    ]);
}

/**
 * POST update annotation
 */
function updateAnnotation() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        jsonError('POST method required', 405);
    }
    
    // Get JSON body
    $body = json_decode(file_get_contents('php://input'), true);
    if (!$body) {
        // Try form data
        $body = $_POST;
    }
    
    $id = intval($body['id'] ?? 0);
    $annotation = $body['annotation'] ?? '';
    
    if ($id <= 0) {
        jsonError('Invalid measurement ID');
    }
    
    $db = getDB();
    $stmt = $db->prepare('UPDATE measurements SET annotation = ? WHERE id = ?');
    $result = $stmt->execute([$annotation, $id]);
    
    jsonResponse([
        'success' => $result,
        'id' => $id,
        'annotation' => $annotation
    ]);
}

/**
 * GET latest measurements
 */
function getLatest() {
    $count = intval(getParam('count', 10));
    $count = min(100, max(1, $count));
    
    $db = getDB();
    $stmt = $db->prepare('
        SELECT id, timestamp, laeq, lmax, lmin, l10, l50, l90,
               spectral_centroid, spectral_flatness, dominant_freq,
               event_count, anomaly_score, annotation
        FROM measurements
        ORDER BY timestamp DESC
        LIMIT ?
    ');
    $stmt->execute([$count]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    // Reverse to chronological order
    $rows = array_reverse($rows);
    
    jsonResponse([
        'count' => count($rows),
        'data' => $rows
    ]);
}

/**
 * GET system status
 */
function getStatus() {
    $db = getDB();
    
    // Get latest measurement timestamp
    $stmt = $db->query('SELECT MAX(timestamp) as latest FROM measurements');
    $latest = $stmt->fetch(PDO::FETCH_ASSOC)['latest'];
    
    // Get total count
    $stmt = $db->query('SELECT COUNT(*) as total FROM measurements');
    $total = $stmt->fetch(PDO::FETCH_ASSOC)['total'];
    
    // Get snippet count
    $stmt = $db->query('SELECT COUNT(*) as snippets FROM measurements WHERE snippet_path IS NOT NULL');
    $snippetCount = $stmt->fetch(PDO::FETCH_ASSOC)['snippets'];
    
    // Get database size
    global $db_path;
    $dbSize = file_exists($db_path) ? filesize($db_path) : 0;
    
    // Get snippets directory size
    $snippetDir = DATA_DIR . '/snippets';
    $snippetSize = 0;
    if (is_dir($snippetDir)) {
        foreach (glob($snippetDir . '/*.ogg') as $file) {
            $snippetSize += filesize($file);
        }
    }
    
    // Check if capture is running (simple heuristic: data within last 2 minutes)
    $captureRunning = $latest && (time() - $latest) < 120;
    
    // Load config to check if snippets are enabled
    $config = loadConfig();
    
    jsonResponse([
        'status' => $captureRunning ? 'running' : 'stopped',
        'latest_timestamp' => $latest,
        'latest_age_seconds' => $latest ? (time() - $latest) : null,
        'total_measurements' => $total,
        'snippet_count' => $snippetCount,
        'snippets_enabled' => $config['save_anomaly_snippets'] ?? false,
        'database_size_bytes' => $dbSize,
        'database_size_mb' => round($dbSize / 1024 / 1024, 2),
        'snippets_size_bytes' => $snippetSize,
        'snippets_size_mb' => round($snippetSize / 1024 / 1024, 2),
        'server_time' => time()
    ]);
}

/**
 * GET list of snippets
 */
function getSnippets() {
    $limit = intval(getParam('limit', 100));
    
    $db = getDB();
    $stmt = $db->prepare('
        SELECT id, timestamp, laeq, lmax, anomaly_score, annotation, snippet_path
        FROM measurements
        WHERE snippet_path IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT ?
    ');
    $stmt->execute([$limit]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    // Check which files actually exist
    foreach ($rows as &$row) {
        $row['file_exists'] = file_exists($row['snippet_path']);
        if ($row['file_exists']) {
            $row['file_size'] = filesize($row['snippet_path']);
        }
    }
    
    jsonResponse([
        'count' => count($rows),
        'data' => $rows
    ]);
}

/**
 * GET serve snippet audio file
 */
function serveSnippet() {
    $id = intval(getParam('id', 0));
    if ($id <= 0) {
        jsonError('Invalid measurement ID');
    }
    
    $db = getDB();
    $stmt = $db->prepare('SELECT snippet_path FROM measurements WHERE id = ?');
    $stmt->execute([$id]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if (!$row || !$row['snippet_path']) {
        jsonError('Snippet not found', 404);
    }
    
    $filepath = $row['snippet_path'];
    if (!file_exists($filepath)) {
        jsonError('Snippet file not found', 404);
    }
    
    // Serve the audio file
    header('Content-Type: audio/ogg');
    header('Content-Length: ' . filesize($filepath));
    header('Content-Disposition: inline; filename="' . basename($filepath) . '"');
    header('Cache-Control: public, max-age=86400');
    
    readfile($filepath);
    exit;
}

/**
 * POST delete snippet
 */
function deleteSnippet() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        jsonError('POST method required', 405);
    }
    
    $body = json_decode(file_get_contents('php://input'), true);
    $id = intval($body['id'] ?? getParam('id', 0));
    
    if ($id <= 0) {
        jsonError('Invalid measurement ID');
    }
    
    $db = getDB();
    
    // Get snippet path
    $stmt = $db->prepare('SELECT snippet_path FROM measurements WHERE id = ?');
    $stmt->execute([$id]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if (!$row || !$row['snippet_path']) {
        jsonError('Snippet not found', 404);
    }
    
    // Delete file if exists
    $filepath = $row['snippet_path'];
    if (file_exists($filepath)) {
        unlink($filepath);
    }
    
    // Clear snippet_path in database
    $stmt = $db->prepare('UPDATE measurements SET snippet_path = NULL WHERE id = ?');
    $stmt->execute([$id]);
    
    jsonResponse([
        'success' => true,
        'id' => $id
    ]);
}

/**
 * Load config file
 */
function loadConfig() {
    $configFile = dirname(__DIR__) . '/config/noisy.json';
    if (file_exists($configFile)) {
        return json_decode(file_get_contents($configFile), true) ?: [];
    }
    return [];
}

/**
 * GET current configuration
 */
function getConfig() {
    $config = loadConfig();
    jsonResponse($config);
}

/**
 * POST save configuration
 */
function saveConfig() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        jsonError('POST method required', 405);
    }
    
    $body = json_decode(file_get_contents('php://input'), true);
    if (!$body) {
        jsonError('Invalid JSON body');
    }
    
    // Load existing config
    $config = loadConfig();
    
    // Only allow updating specific settings
    $allowedKeys = ['save_anomaly_snippets', 'snippet_threshold', 'snippet_duration', 'anomaly_threshold'];
    foreach ($allowedKeys as $key) {
        if (isset($body[$key])) {
            $config[$key] = $body[$key];
        }
    }
    
    // Save config
    $configFile = dirname(__DIR__) . '/config/noisy.json';
    $result = file_put_contents($configFile, json_encode($config, JSON_PRETTY_PRINT));
    
    if ($result === false) {
        jsonError('Failed to save config', 500);
    }
    
    jsonResponse([
        'success' => true,
        'config' => $config,
        'note' => 'Restart capture daemon for changes to take effect'
    ]);
}

