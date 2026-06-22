package main

import (
	"fmt"
	"os"
	"regexp"
	"strings"
)

func parseWorkflowJobs(filePath string) (map[string]workflowJob, error) {
	content, err := os.ReadFile(filePath)
	if err != nil {
		return nil, fmt.Errorf("read workflow %s: %w", filePath, err)
	}

	jobs := make(map[string]workflowJob)
	inJobs := false
	currentKey := ""
	jobRe := regexp.MustCompile(`^  ([A-Za-z0-9_-]+):\s*$`)
	propRe := regexp.MustCompile(`^    ([A-Za-z0-9_-]+):\s*(.*)$`)

	for _, line := range strings.Split(string(content), "\n") {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		if trimmed == "jobs:" {
			inJobs = true
			continue
		}
		if !inJobs {
			continue
		}
		if !strings.HasPrefix(line, " ") {
			break
		}
		if matches := jobRe.FindStringSubmatch(line); len(matches) == 2 {
			currentKey = matches[1]
			jobs[currentKey] = workflowJob{Key: currentKey}
			continue
		}
		if currentKey == "" {
			continue
		}
		if matches := propRe.FindStringSubmatch(line); len(matches) == 3 {
			job := jobs[currentKey]
			switch matches[1] {
			case "name":
				job.Name = strings.Trim(matches[2], `"'`)
			case "uses":
				job.Uses = strings.Trim(matches[2], `"'`)
			}
			jobs[currentKey] = job
		}
	}

	if len(jobs) == 0 {
		return nil, fmt.Errorf("workflow %s has no jobs", filePath)
	}
	return jobs, nil
}
