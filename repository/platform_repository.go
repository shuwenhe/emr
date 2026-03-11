package repository

import (
	"compress/zlib"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "github.com/go-sql-driver/mysql"
	"gopkg.in/yaml.v3"
)

type PlatformRepository struct {
	db *sql.DB
}

type mysqlYAML struct {
	MySQL struct {
		Host     string `yaml:"host"`
		Port     int    `yaml:"port"`
		Database string `yaml:"database"`
		User     string `yaml:"user"`
		Password string `yaml:"password"`
		Charset  string `yaml:"charset"`
	} `yaml:"mysql"`
}

func NewPlatformRepository(mysqlConfigPath, mysqlDSN string) (*PlatformRepository, error) {
	dsn := strings.TrimSpace(mysqlDSN)
	if dsn == "" {
		resolved, err := resolveMySQLConfigPath(mysqlConfigPath)
		if err != nil {
			return nil, err
		}
		cfg, err := loadMySQLYAML(resolved)
		if err != nil {
			return nil, err
		}
		charset := cfg.MySQL.Charset
		if charset == "" {
			charset = "utf8mb4"
		}
		dsn = fmt.Sprintf("%s:%s@tcp(%s:%d)/%s?charset=%s&parseTime=true&loc=Local",
			cfg.MySQL.User,
			cfg.MySQL.Password,
			cfg.MySQL.Host,
			cfg.MySQL.Port,
			cfg.MySQL.Database,
			charset,
		)
	}

	db, err := sql.Open("mysql", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(30 * time.Minute)

	if err := db.Ping(); err != nil {
		_ = db.Close()
		return nil, err
	}

	return &PlatformRepository{db: db}, nil
}

func resolveMySQLConfigPath(input string) (string, error) {
	candidates := []string{}
	if strings.TrimSpace(input) != "" {
		candidates = append(candidates, input)
	}
	candidates = append(candidates, "config/mysql.yaml", "./config/mysql.yaml")

	for _, p := range candidates {
		clean := filepath.Clean(p)
		if _, err := os.Stat(clean); err == nil {
			return clean, nil
		}
	}
	return "", errors.New("mysql_config_not_found")
}

func loadMySQLYAML(path string) (mysqlYAML, error) {
	var cfg mysqlYAML
	raw, err := os.ReadFile(path)
	if err != nil {
		return cfg, err
	}
	if err := yaml.Unmarshal(raw, &cfg); err != nil {
		return cfg, err
	}
	if cfg.MySQL.Host == "" || cfg.MySQL.Port <= 0 || cfg.MySQL.Database == "" || cfg.MySQL.User == "" {
		return cfg, errors.New("invalid_mysql_config")
	}
	return cfg, nil
}

func nowSQL() time.Time {
	return time.Now()
}

func nowISO() string {
	return time.Now().Format("2006-01-02T15:04:05")
}

func decodeJSONCell(raw any) (map[string]any, error) {
	if raw == nil {
		return map[string]any{}, nil
	}

	var data []byte
	switch v := raw.(type) {
	case []byte:
		data = v
	case string:
		data = []byte(v)
	default:
		return map[string]any{}, nil
	}

	if len(data) == 0 {
		return map[string]any{}, nil
	}

	var parsed any
	if err := json.Unmarshal(data, &parsed); err != nil {
		return nil, err
	}

	if s, ok := parsed.(string); ok {
		if strings.HasPrefix(s, "ZLIB_COMPRESSED:") {
			decoded, err := decompressZlibBase64(strings.TrimPrefix(s, "ZLIB_COMPRESSED:"))
			if err != nil {
				return nil, err
			}
			parsed = decoded
		}
	}

	if s, ok := parsed.(string); ok {
		var parsed2 any
		if err := json.Unmarshal([]byte(s), &parsed2); err == nil {
			parsed = parsed2
		}
	}

	if obj, ok := parsed.(map[string]any); ok {
		return obj, nil
	}
	return map[string]any{}, nil
}

func decompressZlibBase64(raw string) (string, error) {
	buf, err := base64.StdEncoding.DecodeString(raw)
	if err != nil {
		return "", err
	}
	zr, err := zlib.NewReader(strings.NewReader(string(buf)))
	if err != nil {
		return "", err
	}
	defer zr.Close()
	out, err := io.ReadAll(zr)
	if err != nil {
		return "", err
	}
	return string(out), nil
}

func (r *PlatformRepository) UpsertPatient(payload map[string]any) (string, error) {
	patientID, _ := payload["patient_id"].(string)
	patientID = strings.TrimSpace(patientID)
	if patientID == "" {
		return "", errors.New("patient_id_required")
	}

	name, _ := payload["name"].(string)
	gender, _ := payload["gender"].(string)
	age := any(nil)
	if v, ok := payload["age"]; ok {
		age = v
	}
	rawPayload, _ := json.Marshal(payload)

	_, err := r.db.Exec(
		`INSERT INTO patients (patient_id, name, gender, age, archived, payload_json, updated_at)
		 VALUES (?, ?, ?, ?, 0, ?, ?)
		 ON DUPLICATE KEY UPDATE
		 name=VALUES(name), gender=VALUES(gender), age=VALUES(age), payload_json=VALUES(payload_json), updated_at=VALUES(updated_at)`,
		patientID, name, gender, age, string(rawPayload), nowSQL(),
	)
	if err != nil {
		return "", err
	}
	return patientID, nil
}

func (r *PlatformRepository) ListPatients(limit, offset int, includeArchived bool) ([]map[string]any, error) {
	rows, err := r.db.Query(
		`SELECT patient_id, name, gender, age, archived, payload_json, updated_at
		 FROM patients
		 WHERE (? = 1 OR archived = 0)
		 ORDER BY updated_at DESC LIMIT ? OFFSET ?`,
		boolToInt(includeArchived), limit, offset,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]map[string]any, 0)
	for rows.Next() {
		var patientID string
		var name sql.NullString
		var gender sql.NullString
		var age sql.NullInt64
		var archived int
		var payloadRaw any
		var updatedAt sql.NullTime
		if err := rows.Scan(&patientID, &name, &gender, &age, &archived, &payloadRaw, &updatedAt); err != nil {
			return nil, err
		}
		payload, _ := decodeJSONCell(payloadRaw)
		payload["patient_id"] = patientID
		payload["name"] = nullString(name)
		payload["gender"] = nullString(gender)
		if age.Valid {
			payload["age"] = age.Int64
		}
		payload["archived"] = archived == 1
		if updatedAt.Valid {
			payload["updated_at"] = updatedAt.Time.Format(time.RFC3339)
		}
		items = append(items, payload)
	}
	return items, rows.Err()
}

func (r *PlatformRepository) GetPatient(patientID string) (map[string]any, bool, error) {
	row := r.db.QueryRow(
		`SELECT patient_id, name, gender, age, archived, payload_json, updated_at
		 FROM patients WHERE patient_id = ?`, patientID,
	)
	var id string
	var name sql.NullString
	var gender sql.NullString
	var age sql.NullInt64
	var archived int
	var payloadRaw any
	var updatedAt sql.NullTime
	if err := row.Scan(&id, &name, &gender, &age, &archived, &payloadRaw, &updatedAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, false, nil
		}
		return nil, false, err
	}
	payload, _ := decodeJSONCell(payloadRaw)
	payload["patient_id"] = id
	payload["name"] = nullString(name)
	payload["gender"] = nullString(gender)
	if age.Valid {
		payload["age"] = age.Int64
	}
	payload["archived"] = archived == 1
	if updatedAt.Valid {
		payload["updated_at"] = updatedAt.Time.Format(time.RFC3339)
	}
	return payload, true, nil
}

func (r *PlatformRepository) ArchivePatient(patientID string, archived bool) (map[string]any, bool, error) {
	res, err := r.db.Exec(`UPDATE patients SET archived = ?, updated_at = ? WHERE patient_id = ?`, boolToInt(archived), nowSQL(), patientID)
	if err != nil {
		return nil, false, err
	}
	affected, _ := res.RowsAffected()
	if affected == 0 {
		return nil, false, nil
	}
	out, ok, err := r.GetPatient(patientID)
	return out, ok, err
}

func (r *PlatformRepository) DeletePatient(patientID string) (bool, error) {
	if _, err := r.db.Exec(`DELETE FROM emrs WHERE patient_id = ?`, patientID); err != nil {
		return false, err
	}
	if _, err := r.db.Exec(`DELETE FROM records WHERE patient_id = ?`, patientID); err != nil {
		return false, err
	}
	res, err := r.db.Exec(`DELETE FROM patients WHERE patient_id = ?`, patientID)
	if err != nil {
		return false, err
	}
	affected, _ := res.RowsAffected()
	return affected > 0, nil
}

func (r *PlatformRepository) GetEMRByID(emrID string) (map[string]any, bool, error) {
	row := r.db.QueryRow(`SELECT emr_json FROM emrs WHERE emr_id = ?`, emrID)
	var emrRaw any
	if err := row.Scan(&emrRaw); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, false, nil
		}
		return nil, false, err
	}
	emr, err := decodeJSONCell(emrRaw)
	if err != nil {
		return nil, false, err
	}
	return emr, true, nil
}

func (r *PlatformRepository) GetEMRByRecordID(recordID string) (map[string]any, bool, error) {
	row := r.db.QueryRow(`SELECT emr_json FROM emrs WHERE record_id = ? LIMIT 1`, recordID)
	var emrRaw any
	if err := row.Scan(&emrRaw); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, false, nil
		}
		return nil, false, err
	}
	emr, err := decodeJSONCell(emrRaw)
	if err != nil {
		return nil, false, err
	}
	return emr, true, nil
}

func (r *PlatformRepository) ListEMRs(patientID, recordID string, limit int, includeArchived bool) ([]map[string]any, error) {
	if strings.TrimSpace(recordID) != "" {
		emr, ok, err := r.GetEMRByRecordID(recordID)
		if err != nil {
			return nil, err
		}
		if !ok {
			return []map[string]any{}, nil
		}
		return []map[string]any{emr}, nil
	}

	where := []string{}
	args := []any{}
	if strings.TrimSpace(patientID) != "" {
		where = append(where, "patient_id = ?")
		args = append(args, patientID)
	}
	if !includeArchived {
		where = append(where, "archived = 0")
	}
	query := `SELECT emr_json FROM emrs`
	if len(where) > 0 {
		query += " WHERE " + strings.Join(where, " AND ")
	}
	query += " ORDER BY created_at DESC LIMIT ?"
	args = append(args, limit)

	rows, err := r.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]map[string]any, 0)
	for rows.Next() {
		var emrRaw any
		if err := rows.Scan(&emrRaw); err != nil {
			return nil, err
		}
		emr, err := decodeJSONCell(emrRaw)
		if err != nil {
			continue
		}
		items = append(items, emr)
	}
	return items, rows.Err()
}

func (r *PlatformRepository) SaveEMR(emr map[string]any) error {
	emrID, _ := emr["emr_id"].(string)
	recordID, _ := emr["record_id"].(string)
	if strings.TrimSpace(emrID) == "" {
		return errors.New("emr_id_required")
	}

	patientID := ""
	if patient, ok := emr["patient"].(map[string]any); ok {
		if v, ok := patient["patient_id"].(string); ok {
			patientID = v
		}
	}

	createdAtStr, _ := emr["created_at"].(string)
	createdAt := nowSQL()
	if createdAtStr != "" {
		if t, err := time.Parse("2006-01-02T15:04:05", createdAtStr); err == nil {
			createdAt = t
		} else if t, err := time.Parse(time.RFC3339, createdAtStr); err == nil {
			createdAt = t
		}
	}

	raw, err := json.Marshal(emr)
	if err != nil {
		return err
	}
	archived := false
	if v, ok := emr["archived"].(bool); ok {
		archived = v
	}

	_, err = r.db.Exec(
		`INSERT INTO emrs (emr_id, record_id, patient_id, created_at, archived, emr_json)
		 VALUES (?, ?, ?, ?, ?, ?)
		 ON DUPLICATE KEY UPDATE
		 record_id=VALUES(record_id), patient_id=VALUES(patient_id), created_at=VALUES(created_at),
		 archived=VALUES(archived), emr_json=VALUES(emr_json)`,
		emrID, recordID, nullableString(patientID), createdAt, boolToInt(archived), string(raw),
	)
	return err
}

func (r *PlatformRepository) GetRecord(recordID string) (map[string]any, bool, error) {
	row := r.db.QueryRow(`SELECT patient_id, metadata_json FROM records WHERE record_id = ? LIMIT 1`, recordID)
	var patientID sql.NullString
	var metadataRaw any
	if err := row.Scan(&patientID, &metadataRaw); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, false, nil
		}
		return nil, false, err
	}
	meta, _ := decodeJSONCell(metadataRaw)
	if patientID.Valid {
		meta["patient_id"] = patientID.String
	}
	return meta, true, nil
}

func (r *PlatformRepository) GetReport(recordID string) (map[string]any, bool, error) {
	row := r.db.QueryRow(`SELECT report_json FROM reports WHERE record_id = ?`, recordID)
	var reportRaw any
	if err := row.Scan(&reportRaw); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, false, nil
		}
		return nil, false, err
	}
	report, err := decodeJSONCell(reportRaw)
	if err != nil {
		return nil, false, err
	}
	return report, true, nil
}

func (r *PlatformRepository) GetPlan(recordID string) (map[string]any, bool, error) {
	row := r.db.QueryRow(`SELECT plan_json FROM plans WHERE record_id = ?`, recordID)
	var planRaw any
	if err := row.Scan(&planRaw); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, false, nil
		}
		return nil, false, err
	}
	plan, err := decodeJSONCell(planRaw)
	if err != nil {
		return nil, false, err
	}
	return plan, true, nil
}

func (r *PlatformRepository) ListRecords(patientID string, limit int) ([]map[string]any, error) {
	query := `SELECT record_id, patient_id, created_at, data_path, metadata_json, image_paths_json FROM records`
	args := []any{}
	if strings.TrimSpace(patientID) != "" {
		query += ` WHERE patient_id = ?`
		args = append(args, patientID)
	}
	query += ` ORDER BY created_at DESC LIMIT ?`
	args = append(args, limit)

	rows, err := r.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]map[string]any, 0)
	for rows.Next() {
		var recordID string
		var pid sql.NullString
		var createdAt sql.NullTime
		var dataPath sql.NullString
		var metadataRaw any
		var imagePathsRaw any
		if err := rows.Scan(&recordID, &pid, &createdAt, &dataPath, &metadataRaw, &imagePathsRaw); err != nil {
			return nil, err
		}

		item := map[string]any{
			"record_id": recordID,
			"patient_id": nullString(pid),
			"data_path": nullString(dataPath),
		}
		if createdAt.Valid {
			item["created_at"] = createdAt.Time.Format(time.RFC3339)
		}
		if metadata, err := decodeJSONCell(metadataRaw); err == nil && len(metadata) > 0 {
			item["metadata_json"] = metadata
		}
		if imagePathsRaw != nil {
			var arr any
			switch v := imagePathsRaw.(type) {
			case []byte:
				_ = json.Unmarshal(v, &arr)
			case string:
				_ = json.Unmarshal([]byte(v), &arr)
			}
			if arr != nil {
				item["image_paths_json"] = arr
			}
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (r *PlatformRepository) Summary() (map[string]any, error) {
	out := map[string]any{}
	for _, target := range []struct {
		Table string
		Key   string
	}{
		{Table: "patients", Key: "patients"},
		{Table: "records", Key: "records"},
		{Table: "reports", Key: "reports"},
		{Table: "emrs", Key: "emrs"},
	} {
		row := r.db.QueryRow("SELECT COUNT(*) AS cnt FROM " + target.Table)
		var cnt int64
		if err := row.Scan(&cnt); err != nil {
			return nil, err
		}
		out[target.Key] = cnt
	}
	return out, nil
}

func boolToInt(v bool) int {
	if v {
		return 1
	}
	return 0
}

func nullString(v sql.NullString) any {
	if v.Valid {
		return v.String
	}
	return nil
}

func nullableString(v string) any {
	if strings.TrimSpace(v) == "" {
		return nil
	}
	return v
}
