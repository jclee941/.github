package main

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
)

func runCmd(name string, args ...string) (string, error) {
	cmd := exec.Command(name, args...)
	cmd.Env = os.Environ()
	out, err := cmd.CombinedOutput()
	return string(out), err
}

func runPythonWithPrefix(prAgentPython, repoReviewPy, repoDir, reviewPath string) error {
	cmd := exec.Command(prAgentPython, repoReviewPy,
		"--repo-path", repoDir,
		"--review-path", reviewPath,
		"--since-commits", fmt.Sprintf("%d", *sinceCommits),
		"--diff-size-limit", fmt.Sprintf("%d", *diffSizeLimit),
		"--model", *model,
		"--response-language", "ko",
	)
	cmd.Env = os.Environ()

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return err
	}

	if err := cmd.Start(); err != nil {
		return err
	}

	go prefixLines(stdout, "  [pr-agent] ")
	go prefixLines(stderr, "  [pr-agent] ")

	return cmd.Wait()
}

func prefixLines(r io.Reader, prefix string) {
	buf := make([]byte, 4096)
	for {
		n, err := r.Read(buf)
		if n > 0 {
			chunk := string(buf[:n])
			lines := strings.Split(chunk, "\n")
			for i, line := range lines {
				if i == len(lines)-1 && !strings.HasSuffix(chunk, "\n") {
					fmt.Printf("%s%s", prefix, line)
					continue
				}
				fmt.Printf("%s%s\n", prefix, line)
			}
		}
		if err != nil {
			break
		}
	}
}
