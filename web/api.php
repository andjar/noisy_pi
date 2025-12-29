<?php
/**
 * Noisy Pi API - Enhanced
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

$action = $_GET['action'] ?? 'recent';

switch ($action) {
    case 'recent':
        $limit = intval($_GET['limit'] ?? 100);
        $limit = min(max($limit, 1), 10000);
        
        $db = get_db();
        $stmt = $db->prepare('
            SELECT id, timestamp, unix_time, mean_db, max_db, min_db,
                   l10_db, l50_db, l90_db,
                   band_0_200, band_200_500, band_500_1k, band_1k_2k,
                   band_2k_4k, band_4k_8k, band_8k_24k,
                   band_0_100, band_100_300, band_300_800, band_800_1500,
                   band_1500_3k, band_3k_6k, band_6k_12k, band_12k_24k,
                   spectral_centroid, spectral_flatness, dominant_freq,
                   silence_pct, dynamic_range,
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
        $start = $_GET['start'] ?? date('Y-m-d', strtotime('-7 days'));
        $end = $_GET['end'] ?? date('Y-m-d');
        
        $db = get_db();
        $stmt = $db->prepare('
            SELECT id, timestamp, unix_time, mean_db, max_db, min_db,
                   l10_db, l50_db, l90_db,
                   band_0_200, band_200_500, band_500_1k, band_1k_2k,
                   band_2k_4k, band_4k_8k, band_8k_24k,
                   band_0_100, band_100_300, band_300_800, band_800_1500,
                   band_1500_3k, band_3k_6k, band_6k_12k, band_12k_24k,
                   spectral_centroid, spectral_flatness, dominant_freq,
                   silence_pct, dynamic_range,
                   anomaly_score, annotation, sample_seconds, status
            FROM measurements
            WHERE date(timestamp) >= :start AND date(timestamp) <= :end
            ORDER BY unix_time ASC
        ');
        $stmt->bindValue(':start', $start, SQLITE3_TEXT);
        $stmt->bindValue(':end', $end, SQLITE3_TEXT);
        $result = $stmt->execute();
        
        $rows = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
            $rows[] = $row;
        }
        
        echo json_encode(['data' => $rows, 'count' => count($rows)]);
        break;
        
    case 'spectrogram':
        $id = intval($_GET['id'] ?? 0);
        if ($id <= 0) {
            http_response_code(400);
            echo json_encode(['error' => 'Invalid ID']);
            exit;
        }
        
        $db = get_db();
        $stmt = $db->prepare('
            SELECT spectrogram, spectrogram_snapshots, spectrogram_bins, timestamp
            FROM measurements WHERE id = :id
        ');
        $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
        $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
        
        if (!$row || !$row['spectrogram']) {
            http_response_code(404);
            echo json_encode(['error' => 'Spectrogram not found']);
            exit;
        }
        
        $compressed = $row['spectrogram'];
        $decompressed = @gzuncompress($compressed);
        
        if ($decompressed === false) {
            http_response_code(500);
            echo json_encode(['error' => 'Failed to decompress']);
            exit;
        }
        
        $n_snapshots = $row['spectrogram_snapshots'] ?: 10;
        $n_bins = $row['spectrogram_bins'] ?: 256;
        
        // Convert to array of arrays (dequantize)
        $data = [];
        $bytes = unpack('C*', $decompressed);
        $idx = 1;
        for ($s = 0; $s < $n_snapshots; $s++) {
            $spectrum = [];
            for ($b = 0; $b < $n_bins; $b++) {
                if (isset($bytes[$idx])) {
                    // Dequantize: 0-255 -> -90 to 10 dB
                    $spectrum[] = round(($bytes[$idx] / 255.0) * 100 - 90, 1);
                    $idx++;
                }
            }
            $data[] = $spectrum;
        }
        
        echo json_encode([
            'data' => $data,
            'snapshots' => $n_snapshots,
            'bins' => $n_bins,
            'timestamp' => $row['timestamp'],
            'freq_max' => 24000
        ]);
        break;
        
    case 'stats':
        $period = $_GET['period'] ?? '1h';
        
        $db = get_db();
        
        switch ($period) {
            case '1h': $seconds = 3600; break;
            case '6h': $seconds = 21600; break;
            case '24h': $seconds = 86400; break;
            case '7d': $seconds = 604800; break;
            case '30d': $seconds = 2592000; break;
            case 'all': $seconds = 0; break;
            default: $seconds = 3600;
        }
        
        if ($seconds > 0) {
            $threshold = time() - $seconds;
            $where = "WHERE unix_time >= :threshold";
        } else {
            $threshold = 0;
            $where = "";
        }
        
        $sql = "
            SELECT 
                AVG(mean_db) as avg_db,
                MAX(max_db) as max_db,
                MIN(min_db) as min_db,
                AVG(silence_pct) as avg_silence,
                AVG(band_0_200) as avg_band_0_200,
                AVG(band_200_500) as avg_band_200_500,
                AVG(band_500_1k) as avg_band_500_1k,
                AVG(band_1k_2k) as avg_band_1k_2k,
                AVG(band_2k_4k) as avg_band_2k_4k,
                AVG(band_4k_8k) as avg_band_4k_8k,
                AVG(band_8k_24k) as avg_band_8k_24k,
                AVG(spectral_centroid) as avg_centroid,
                COUNT(*) as count,
                SUM(CASE WHEN anomaly_score >= 2.5 THEN 1 ELSE 0 END) as anomalies
            FROM measurements
            $where
        ";
        
        $stmt = $db->prepare($sql);
        if ($seconds > 0) {
            $stmt->bindValue(':threshold', $threshold, SQLITE3_INTEGER);
        }
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
                AVG(spectral_centroid) as avg_centroid,
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
        
        // Check if baseline table exists
        $check = $db->querySingle("SELECT name FROM sqlite_master WHERE type='table' AND name='baseline'");
        if (!$check) {
            echo json_encode(['data' => [], 'error' => 'No baseline data yet']);
            exit;
        }
        
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
            FROM snippets ORDER BY timestamp DESC LIMIT 50
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
        $stmt = $db->prepare('SELECT filename FROM snippets WHERE id = :id');
        $stmt->bindValue(':id', $id, SQLITE3_INTEGER);
        $row = $stmt->execute()->fetchArray(SQLITE3_ASSOC);
        
        if ($row) {
            $filepath = $snippets_dir . '/' . $row['filename'];
            if (file_exists($filepath)) unlink($filepath);
            
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
        $config = json_decode(file_get_contents($config_path), true);
        // Only expose safe config options
        echo json_encode([
            'anomaly_threshold' => $config['anomaly_threshold'] ?? 2.5,
            'snippet_enabled' => $config['snippet_enabled'] ?? false,
            'snippet_duration' => $config['snippet_duration'] ?? 5,
            'refresh_interval' => $config['refresh_interval'] ?? 30
        ]);
        break;
        
    case 'save_config':
        if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
            http_response_code(405);
            echo json_encode(['error' => 'POST required']);
            exit;
        }
        
        if (!file_exists($config_path)) {
            http_response_code(404);
            echo json_encode(['error' => 'Config not found', 'path' => $config_path]);
            exit;
        }
        
        if (!is_writable($config_path)) {
            http_response_code(500);
            echo json_encode(['error' => 'Config file not writable', 'path' => $config_path, 'hint' => 'Run: sudo chmod 666 ' . $config_path]);
            exit;
        }
        
        $input = json_decode(file_get_contents('php://input'), true);
        if ($input === null) {
            http_response_code(400);
            echo json_encode(['error' => 'Invalid JSON input']);
            exit;
        }
        
        $config = json_decode(file_get_contents($config_path), true);
        if ($config === null) {
            http_response_code(500);
            echo json_encode(['error' => 'Failed to parse config file']);
            exit;
        }
        
        // Only allow updating specific fields
        $allowed = ['anomaly_threshold', 'snippet_enabled', 'snippet_duration', 'refresh_interval'];
        foreach ($allowed as $key) {
            if (isset($input[$key])) {
                $config[$key] = $input[$key];
            }
        }
        
        $result = file_put_contents($config_path, json_encode($config, JSON_PRETTY_PRINT));
        
        if ($result === false) {
            http_response_code(500);
            echo json_encode(['error' => 'Failed to write config', 'path' => $config_path]);
            exit;
        }
        
        echo json_encode(['success' => true]);
        break;
        
    case 'export':
        $format = $_GET['format'] ?? 'csv';
        $start = $_GET['start'] ?? date('Y-m-d', strtotime('-7 days'));
        $end = $_GET['end'] ?? date('Y-m-d');
        
        $db = get_db();
        $stmt = $db->prepare('
            SELECT timestamp, mean_db, max_db, min_db,
                   l10_db, l50_db, l90_db,
                   band_0_200, band_200_500, band_500_1k, band_1k_2k,
                   band_2k_4k, band_4k_8k, band_8k_24k,
                   spectral_centroid, spectral_flatness, dominant_freq,
                   silence_pct, anomaly_score, annotation
            FROM measurements
            WHERE date(timestamp) >= :start AND date(timestamp) <= :end
            ORDER BY unix_time ASC
        ');
        $stmt->bindValue(':start', $start, SQLITE3_TEXT);
        $stmt->bindValue(':end', $end, SQLITE3_TEXT);
        $result = $stmt->execute();
        
        header('Content-Type: text/csv');
        header('Content-Disposition: attachment; filename="noisy_pi_' . $start . '_' . $end . '.csv"');
        
        $first = true;
        $output = fopen('php://output', 'w');
        
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
            if ($first) {
                fputcsv($output, array_keys($row));
                $first = false;
            }
            fputcsv($output, $row);
        }
        
        fclose($output);
        exit;
        
    default:
        http_response_code(400);
        echo json_encode(['error' => 'Unknown action: ' . $action]);
}
