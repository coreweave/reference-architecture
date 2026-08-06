//go:build linux

package repair

import (
	"fmt"
	"strings"
	"syscall"
)

// EnsureHierarchy creates only absent directory components under /mnt/local, anchored by FDs.
func EnsureHierarchy(expected string) error {
	return ensureHierarchy(HostRoot, expected)
}

func ensureHierarchy(hostRoot, expected string) error {
	prefix := hostRoot + "/"
	if !strings.HasPrefix(expected, prefix) || strings.TrimPrefix(expected, prefix) == "" {
		return fmt.Errorf("path escapes host root")
	}
	root, err := syscall.Open(hostRoot, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if err != nil {
		return err
	}
	defer syscall.Close(root)
	var rootStat syscall.Stat_t
	if err = syscall.Fstat(root, &rootStat); err != nil {
		return err
	}
	fd := root
	for _, part := range strings.Split(strings.TrimPrefix(expected, prefix), "/") {
		if part == "" || part == "." || part == ".." {
			return fmt.Errorf("unsafe path component")
		}
		next, openErr := syscall.Openat(fd, part, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
		created := false
		if openErr == syscall.ENOENT {
			if err = syscall.Mkdirat(fd, part, 0770); err != nil {
				if err != syscall.EEXIST {
					return err
				}
			} else {
				created = true
			}
			next, openErr = syscall.Openat(fd, part, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
		}
		if openErr != nil {
			return openErr
		}
		var st syscall.Stat_t
		if err = syscall.Fstat(next, &st); err != nil {
			syscall.Close(next)
			return err
		}
		if st.Dev != rootStat.Dev {
			syscall.Close(next)
			return fmt.Errorf("cross-mount component %q", part)
		}
		if created {
			if err = syscall.Fchmod(next, 0770); err != nil {
				syscall.Close(next)
				return err
			}
			if err = syscall.Fchown(next, 1001, 0); err != nil {
				syscall.Close(next)
				return err
			}
		}
		if fd != root {
			syscall.Close(fd)
		}
		fd = next
	}
	if fd != root {
		defer syscall.Close(fd)
	}
	return nil
}
