package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

type workflowJob struct {
	Key  string
	Name string
	Uses string
}

// notifyOnFailureRequiresCheckout enforces a deployment invariant: any job that
// uses the local composite action ./.github/actions/notify-on-failure MUST run
// an actions/checkout step (to a non-custom path) BEFORE it, otherwise the
// composite action file is absent on the runner workspace and the notify step
// itself fails. A custom `path:` checkout (e.g. path: pr-agent-src) does NOT
// satisfy this because the action is resolved from the workspace root.
func (v *validator) notifyOnFailureRequiresCheckout() error {
	dirs := []string{
		filepath.Join(v.rootDir, ".github", "workflows"),
		filepath.Join(v.rootDir, ".github", "workflows", "security"),
	}
	var files []string
	for _, d := range dirs {
		entries, err := os.ReadDir(d)
		if err != nil {
			continue
		}
		for _, e := range entries {
			if e.IsDir() {
				continue
			}
			if strings.HasSuffix(e.Name(), ".yml") || strings.HasSuffix(e.Name(), ".yaml") {
				files = append(files, filepath.Join(d, e.Name()))
			}
		}
	}
	sort.Strings(files)

	jobRe := regexp.MustCompile(`^  ([A-Za-z0-9_-]+):\s*$`)
	stepRe := regexp.MustCompile(`^      - `)
	checkoutRe := regexp.MustCompile(`uses:\s*actions/checkout@`)
	pathRe := regexp.MustCompile(`^          path:\s*\S`)
	notifyRe := regexp.MustCompile(`uses:\s*\./\.github/actions/notify-on-failure`)

	var offenders []string
	for _, f := range files {
		content, err := os.ReadFile(f)
		if err != nil {
			return fmt.Errorf("read workflow %s: %w", f, err)
		}
		lines := strings.Split(string(content), "\n")
		inJobs := false
		currentJob := ""
		// per-job state
		sawDefaultCheckout := false
		inCheckoutStep := false
		checkoutHasPath := false
		flushCheckout := func() {
			if inCheckoutStep && !checkoutHasPath {
				sawDefaultCheckout = true
			}
			inCheckoutStep = false
			checkoutHasPath = false
		}
		for _, line := range lines {
			trimmed := strings.TrimSpace(line)
			if trimmed == "jobs:" {
				inJobs = true
				continue
			}
			if !inJobs {
				continue
			}
			if m := jobRe.FindStringSubmatch(line); len(m) == 2 {
				flushCheckout()
				currentJob = m[1]
				sawDefaultCheckout = false
				continue
			}
			if currentJob == "" {
				continue
			}
			if stepRe.MatchString(line) {
				flushCheckout()
			}
			if checkoutRe.MatchString(line) {
				inCheckoutStep = true
			}
			if inCheckoutStep && pathRe.MatchString(line) {
				checkoutHasPath = true
			}
			if notifyRe.MatchString(line) && !sawDefaultCheckout {
				offenders = append(offenders, fmt.Sprintf("%s :: job %q", filepath.Base(f), currentJob))
			}
		}
		flushCheckout()
	}

	if len(offenders) > 0 {
		return fmt.Errorf("jobs use ./.github/actions/notify-on-failure without a prior default-path checkout: %s", strings.Join(offenders, "; "))
	}
	return nil
}

// noOrgEndpointForUserAccount guards against a recurring bug: jclee941 is a
// USER account, not an organization, so `gh api orgs/jclee941/...` returns 404
// and silently (2>/dev/null) yields empty repo lists or hard-fails matrix jobs.
// All repo discovery must use the users/ endpoint.
func (v *validator) noOrgEndpointForUserAccount() error {
	dirs := []string{
		filepath.Join(v.rootDir, ".github", "workflows"),
		filepath.Join(v.rootDir, ".github", "workflows", "security"),
	}
	var offenders []string
	for _, d := range dirs {
		entries, err := os.ReadDir(d)
		if err != nil {
			continue
		}
		for _, e := range entries {
			if e.IsDir() || !(strings.HasSuffix(e.Name(), ".yml") || strings.HasSuffix(e.Name(), ".yaml")) {
				continue
			}
			p := filepath.Join(d, e.Name())
			b, err := os.ReadFile(p)
			if err != nil {
				return fmt.Errorf("read workflow %s: %w", p, err)
			}
			if strings.Contains(string(b), "orgs/jclee941") {
				offenders = append(offenders, e.Name())
			}
		}
	}
	if len(offenders) > 0 {
		return fmt.Errorf("workflows query the orgs/ endpoint for the jclee941 USER account (use users/jclee941): %s", strings.Join(offenders, ", "))
	}
	return nil
}
