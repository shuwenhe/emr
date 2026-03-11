package repository

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"report-file-service/model"
)

type FSRepository struct {
	reportsDir string
}

var dayDirRegex = regexp.MustCompile(`^\d{8}$`)

func NewFSRepository(reportsDir string) (*FSRepository, error) {
	cleanDir := filepath.Clean(reportsDir)
	if err := os.MkdirAll(cleanDir, 0o755); err != nil {
		return nil, fmt.Errorf("create reports dir: %w", err)
	}
	return &FSRepository{reportsDir: cleanDir}, nil
}

func (r *FSRepository) ListReports(date string, trash bool) ([]model.ReportFile, error) {
	root, err := r.listRoot(date, trash)
	if err != nil {
		return nil, err
	}

	reports := make([]model.ReportFile, 0)
	if date != "" {
		reports, err = r.collectFromDay(root, date, trash)
		if err != nil {
			return nil, err
		}
	} else {
		err = filepath.WalkDir(root, func(path string, d fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if path == root {
				return nil
			}
			if d.IsDir() {
				if strings.HasPrefix(d.Name(), ".") {
					return filepath.SkipDir
				}
				relPath, err := filepath.Rel(root, path)
				if err != nil {
					return err
				}
				if relPath != "." && strings.Count(relPath, string(filepath.Separator)) == 0 && !dayDirRegex.MatchString(d.Name()) {
					return filepath.SkipDir
				}
				return nil
			}
			relPath, err := filepath.Rel(root, path)
			if err != nil {
				return err
			}
			parts := strings.Split(relPath, string(filepath.Separator))
			if len(parts) != 2 {
				return nil
			}
			if !dayDirRegex.MatchString(parts[0]) {
				return nil
			}
			ext := strings.ToLower(filepath.Ext(parts[1]))
			if ext != ".pdf" && ext != ".docx" {
				return nil
			}
			info, err := d.Info()
			if err != nil {
				return err
			}
			day := parts[0]
			name := parts[1]
			url := buildURL(day, name, trash)
			reports = append(reports, model.ReportFile{
				Date:      day,
				Name:      name,
				SizeBytes: info.Size(),
				URL:       url,
				UpdatedAt: info.ModTime().Unix(),
			})
			return nil
		})
		if err != nil {
			return nil, fmt.Errorf("walk reports: %w", err)
		}
	}

	sort.Slice(reports, func(i, j int) bool {
		return reports[i].UpdatedAt > reports[j].UpdatedAt
	})

	return reports, nil
}

func (r *FSRepository) ResolveReportPath(date, filename string, trash bool) (string, error) {
	if date == "" || filename == "" {
		return "", errors.New("date and filename are required")
	}

	baseRoot := r.reportsDir
	if trash {
		baseRoot = filepath.Join(r.reportsDir, ".trash")
	}

	baseAbs, err := filepath.Abs(baseRoot)
	if err != nil {
		return "", err
	}

	candidate := filepath.Join(baseRoot, date, filename)
	candidateAbs, err := filepath.Abs(candidate)
	if err != nil {
		return "", err
	}

	rel, err := filepath.Rel(baseAbs, candidateAbs)
	if err != nil {
		return "", err
	}
	if strings.HasPrefix(rel, "..") || rel == "." {
		return "", errors.New("invalid_report_path")
	}

	return candidateAbs, nil
}

func (r *FSRepository) ArchiveReport(date, filename string, archived bool) (string, error) {
	sourceTrash := !archived
	targetTrash := archived
	status := "restored"
	if archived {
		status = "archived"
	}

	srcPath, err := r.ResolveReportPath(date, filename, sourceTrash)
	if err != nil {
		return "", err
	}
	dstPath, err := r.ResolveReportPath(date, filename, targetTrash)
	if err != nil {
		return "", err
	}

	if _, err := os.Stat(srcPath); err != nil {
		if os.IsNotExist(err) {
			if archived {
				return "", errors.New("report_not_found")
			}
			return "", errors.New("report_not_archived")
		}
		return "", err
	}

	if !archived {
		if _, err := os.Stat(dstPath); err == nil {
			return "", errors.New("report_already_exists")
		} else if !os.IsNotExist(err) {
			return "", err
		}
	}

	if err := os.MkdirAll(filepath.Dir(dstPath), 0o755); err != nil {
		return "", err
	}
	if err := os.Rename(srcPath, dstPath); err != nil {
		return "", err
	}
	return status, nil
}

func (r *FSRepository) listRoot(date string, trash bool) (string, error) {
	root := r.reportsDir
	if trash {
		root = filepath.Join(r.reportsDir, ".trash")
	}
	if date != "" {
		root = filepath.Join(root, date)
	}

	if err := os.MkdirAll(root, 0o755); err != nil {
		return "", err
	}
	return root, nil
}

func (r *FSRepository) collectFromDay(dayRoot, day string, trash bool) ([]model.ReportFile, error) {
	entries, err := os.ReadDir(dayRoot)
	if err != nil {
		if os.IsNotExist(err) {
			return []model.ReportFile{}, nil
		}
		return nil, err
	}

	reports := make([]model.ReportFile, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		ext := strings.ToLower(filepath.Ext(entry.Name()))
		if ext != ".pdf" && ext != ".docx" {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			return nil, err
		}
		name := entry.Name()
		reports = append(reports, model.ReportFile{
			Date:      day,
			Name:      name,
			SizeBytes: info.Size(),
			URL:       buildURL(day, name, trash),
			UpdatedAt: info.ModTime().Unix(),
		})
	}
	return reports, nil
}

func buildURL(day, name string, trash bool) string {
	if trash {
		return "/v1/reports/trash/" + day + "/" + name
	}
	return "/v1/reports/" + day + "/" + name
}
