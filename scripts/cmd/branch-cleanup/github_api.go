package main

import (
	"bytes"
	"fmt"
	"net/url"
	"os/exec"
	"strings"
)

func listOpenPRHeads(fullRepo string) (map[string]struct{}, error) {
	output, err := ghOutput(
		"pr", "list",
		"--repo", fullRepo,
		"--state", "open",
		"--json", "headRefName",
		"--limit", "100",
		"--jq", ".[].headRefName",
	)
	if err != nil {
		return nil, err
	}

	heads := make(map[string]struct{})
	for _, line := range strings.Split(output, "\n") {
		head := strings.TrimSpace(line)
		if head != "" {
			heads[head] = struct{}{}
		}
	}
	return heads, nil
}

func deleteBranch(fullRepo, branch string) error {
	endpoint := fmt.Sprintf("repos/%s/git/refs/heads/%s", fullRepo, url.PathEscape(branch))
	_, err := ghOutput("api", "-X", "DELETE", endpoint, "--silent")
	return err
}

func ghOutput(args ...string) (string, error) {
	cmd := exec.Command("gh", args...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		if stderr.Len() > 0 {
			return "", fmt.Errorf("%s: %s", err, strings.TrimSpace(stderr.String()))
		}
		return "", err
	}
	return stdout.String(), nil
}
