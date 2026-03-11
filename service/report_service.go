package service

import (
	"fmt"

	"report-file-service/cache"
	"report-file-service/model"
	"report-file-service/repository"
)

type ReportService struct {
	repo  *repository.FSRepository
	cache *cache.TTLCache
}

func NewReportService(repo *repository.FSRepository, cache *cache.TTLCache) *ReportService {
	return &ReportService{repo: repo, cache: cache}
}

func (s *ReportService) ListReports(date string, trash bool) ([]model.ReportFile, error) {
	key := listCacheKey(date, trash)
	if cached, ok := s.cache.Get(key); ok {
		if data, valid := cached.([]model.ReportFile); valid {
			return data, nil
		}
	}

	reports, err := s.repo.ListReports(date, trash)
	if err != nil {
		return nil, err
	}
	s.cache.Set(key, reports)
	return reports, nil
}

func (s *ReportService) ResolveReportPath(date, filename string, trash bool) (string, error) {
	return s.repo.ResolveReportPath(date, filename, trash)
}

func (s *ReportService) ArchiveReport(req model.ArchiveRequest) (model.ArchiveResponse, error) {
	status, err := s.repo.ArchiveReport(req.Date, req.Filename, req.Archived)
	if err != nil {
		return model.ArchiveResponse{}, err
	}

	s.invalidateReportCache(req.Date)

	return model.ArchiveResponse{
		Status:   status,
		Date:     req.Date,
		Filename: req.Filename,
	}, nil
}

func (s *ReportService) invalidateReportCache(date string) {
	keys := []string{
		listCacheKey("", false),
		listCacheKey(date, false),
		listCacheKey("", true),
		listCacheKey(date, true),
	}
	for _, key := range keys {
		s.cache.Delete(key)
	}
}

func listCacheKey(date string, trash bool) string {
	typeTag := "reports"
	if trash {
		typeTag = "trash"
	}
	if date == "" {
		date = "all"
	}
	return fmt.Sprintf("%s:%s", typeTag, date)
}
