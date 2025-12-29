<?php
/**
 * Noisy Pi API
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    exit(0);
}

$db_path = getenv('NOISY_DATA_DIR') ?: '/var/lib/noisy-pi';
$db_file = $db_path . '/noisy.db';
$config_path = (getenv('NOISY_CONFIG_DIR') ?: '/opt/noisy-pi/config') . '/noisy.json';
$snippets_dir = $db_path . '/snippets';

// Open database
function get_db($readonly = true) {
    global $db_file;
    if (!file_exists($db_file)) {
        http_response_code(503);
        echo json_encode(['error' => 'Database not found', 'path' => $db_file]);
        exit;
    }
    $flags = $readonly ? SQLITE3_OPEN_READONLY : SQLITE3_OPEN_READWRITE;
    return new SQLite3($db_file, $flags);
}

// Get request parameter
$action = $_GET['action'] ?? 'recent';

switch ($action) {
    case 'recent':
        $limit = intval($_GET['limit'] ?? 100);
        $limit = min(max($limit, 1), 5000);
        
        $db = get_db();
        $stmt = $db->prepare('
            SELECT id, timestamp, unix_time, mean_db, max_db, min_db,
                   l10_db, l50_db, l90_db,
                   band_low_db, band_mid_db, band_high_db,
                   silence_pct, peak_freq_hz, crest_factor, dynamic_range,
                   anomaly_score, annotation, sample_seconds, status
            FROM measurements
            ORDER BY unix_time DESC
            LIMIT :limit
        ');
        $stmt->bindValue(':limit', $limit, SQLITE3_INTEGER);
        $result = $stmt->execute();
        
        $rows = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
            $rows[] = $row;
        }
        
        echo json_encode(['data' => $rows]);
        break;
        
    case 'range':
        $start = $_GET['start'] ?? date('Y-m-d', strtotime('-1 day'));
        $end = $_GET['end'] ?? date('Y-m-d');
        
        $db = get_db();
        $stmt = $db->prepare('
            SELECT timestamp, unix_time, mean_db, max_db, min_db,
                   band_low_db, band_mid_db, band_high_db,
                   silence_pct, anomaly_score
            FROM measurements
            WHERE timestamp >= :start AND timestamp < :end
            ORDER BY timestamp ASC
        ');
        $stmt->bindValue(':start', $start, SQLITE3_TEXT);
        $stmt->bindValue(':end', $end . ' 23:59:59', SQLITE3_TEXT);
        $result = $stmt->execute();
        
        $rows = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
            $rows[] = $row;
        }
        
        echo json_encode(['data' => $rows]);
        break;
        
    case 'stats':
        $period = $_GET['period'] ?? '1h';
        
        $db = get_db();
        
        // Calculate time threshold
        switch ($period) {
            case '1h': $seconds = 3600; break;
            case '6h': $seconds = 21600; break;
            case '24h': $seconds = 86400; break;
            case '7d': $seconds = 604800; break;
            default: $seconds = 3600;
        }
        $threshold = time() - $seconds;
        
        $stmt = $db->prepare('
            SELECT 
                AVG(mean_db) as avg_db,
                MAX(max_db) as max_db,
                MIN(min_db) as min_db,
                AVG(silence_pct) as avg_silence,
                AVG(band_low_db) as avg_band_low,
                AVG(band_mid_db) as avg_band_mid,
                AVG(band_high_db) as avg_band_high,
                COUNT(*) as count,
                SUM(CASE WHEN anomaly_score >= 2.5 THEN 1 ELSE 0 END) as anomalies
            FROM measurements
            WHERE unix_time >= :threshold
        ');
        $stmt->bindValue(':threshold', $threshold, SQLITE3_INTEGER);
        $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
        
        echo json_encode(['data' => $row]);
        break;
        
    case 'today_anomalies':
        $db = get_db();
        $today = date('Y-m-d');
        
        $stmt = $db->prepare('
            SELECT COUNT(*) as count
            FROM measurements
            WHERE timestamp >= :today AND anomaly_score >= 2.5
        ');
        $stmt->bindValue(':today', $today, SQLITE3_TEXT);
        $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
        
        echo json_encode(['count' => intval($row['count'])]);
        break;
        
    case 'hourly_stats':
        $db = get_db();
        $today = date('Y-m-d');
        
        $stmt = $db->prepare("
            SELECT 
                strftime('%H', timestamp) as hour,
                AVG(mean_db) as avg_db,
                MAX(max_db) as max_db,
                MIN(min_db) as min_db,
                COUNT(*) as count,
                SUM(CASE WHEN anomaly_score >= 2.5 THEN 1 ELSE 0 END) as anomaly_count
            FROM measurements
            WHERE timestamp >= :today
            GROUP BY strftime('%H', timestamp)
            ORDER BY hour ASC
        ");
        $stmt->bindValue(':today', $today, SQLITE3_TEXT);
        $result = $stmt->execute();
        
        $rows = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
            $row['hour'] = intval($row['hour']);
            $rows[] = $row;
        }
        
        echo json_encode(['data' => $rows]);
        break;
        
    case 'baseline':
        $db = get_db();
        $result = $db->query('
            SELECT day_of_week, hour, mean_db_avg, mean_db_std, samples
            FROM baseline
            ORDER BY day_of_week, hour
        ');
        
        $rows = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
            $rows[] = $row;
        }
        
        echo json_encode(['data' => $rows]);
        break;
        
    case 'annotate':
        if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
            http_response_code(405);
            echo json_encode(['error' => 'POST required']);
            exit;
        }
        
        $input = json_decode(file_get_contents('php://input'), true);
        $id = intval($input['id'] ?? 0);
        $annotation = $input['annotation'] ?? '';
        
        if ($id <= 0) {
            http_response_code(400);
            echo json_encode(['error' => 'Invalid ID']);
            exit;
        }
        
        $db = get_db(false);
        $stmt = $db->prepare('UPDATE measurements SET annotation = :annotation WHERE id = :id');
        $stmt->bindValue(':annotation', $annotation, SQLITE3_TEXT);
        $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
        $stmt->execute();
        
        echo json_encode(['success' => true]);
        break;
        
    case 'snippets':
        $db = get_db();
        $stmt = $db->prepare('
            SELECT id, timestamp, filename, anomaly_score, measurement_id
            FROM snippets
            ORDER BY timestamp DESC
            LIMIT 50
        ');
        $result = $stmt->execute();
        
        $rows = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
            $filepath = $snippets_dir . '/' . $row['filename'];
            if (file_exists($filepath)) {
                $row['url'] = 'api.php?action=snippet_audio&file=' . urlencode($row['filename']);
                $rows[] = $row;
            }
        }
        
        echo json_encode(['data' => $rows]);
        break;
        
    case 'snippet_audio':
        $file = basename($_GET['file'] ?? '');
        $filepath = $snippets_dir . '/' . $file;
        
        if (!$file || !file_exists($filepath)) {
            http_response_code(404);
            echo json_encode(['error' => 'File not found']);
            exit;
        }
        
        header('Content-Type: audio/ogg');
        header('Content-Length: ' . filesize($filepath));
        header('Cache-Control: public, max-age=86400');
        readfile($filepath);
        exit;
        
    case 'delete_snippet':
        if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
            http_response_code(405);
            echo json_encode(['error' => 'POST required']);
            exit;
        }
        
        $input = json_decode(file_get_contents('php://input'), true);
        $id = intval($input['id'] ?? 0);
        
        if ($id <= 0) {
            http_response_code(400);
            echo json_encode(['error' => 'Invalid ID']);
            exit;
        }
        
        $db = get_db(false);
        
        // Get filename first
        $stmt = $db->prepare('SELECT filename FROM snippets WHERE id = :id');
        $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
        $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
        
        if ($row) {
            // Delete file
            $filepath = $snippets_dir . '/' . $row['filename'];
            if (file_exists($filepath)) {
                unlink($filepath);
            }
            
            // Delete database entry
            $stmt = $db->prepare('DELETE FROM snippets WHERE id = :id');
            $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
            $stmt->execute();
        }
        
        echo json_encode(['success' => true]);
        break;
        
    case 'config':
        if (!file_exists($config_path)) {
            echo json_encode(['error' => 'Config not found']);
            exit;
        }
        echo file_get_contents($config_path);
        break;
        
    case 'save_config':
        if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
            http_response_code(405);
            echo json_encode(['error' => 'POST required']);
            exit;
        }
        
        $input = json_decode(file_get_contents('php://input'), true);
        if (!$input) {
            http_response_code(400);
            echo json_encode(['error' => 'Invalid JSON']);
            exit;
        }
        
        // Merge with existing config
        $existing = [];
        if (file_exists($config_path)) {
            $existing = json_decode(file_get_contents($config_path), true) ?? [];
        }
        
        $merged = array_merge($existing, $input);
        
        if (file_put_contents($config_path, json_encode($merged, JSON_PRETTY_PRINT))) {
            echo json_encode(['success' => true]);
        } else {
            http_response_code(500);
            echo json_encode(['error' => 'Failed to save config']);
        }
        break;
        
    default:
        http_response_code(400);
        echo json_encode(['error' => 'Unknown action: ' . $action]);
}
