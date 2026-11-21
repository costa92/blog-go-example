// tz-verify 在目标镜像内校验：tzdata.zi 中的每个时区别名都能加载，
// 且与其标准名在 1970–2037 的偏移、缩写一致。不引入 time/tzdata，和服务一样只用系统数据。
// 任一失败退出码为 1，用于让 docker build 失败。
package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const zoneDir = "/usr/share/zoneinfo"

// 必须出现在 tzdata.zi 中的别名，防止清单读漏：15 个 Asia/Europe 旧名和事故里出现过的美洲旧名。
var required = []string{
	"Asia/Ashkhabad", "Asia/Calcutta", "Asia/Choibalsan", "Asia/Chungking",
	"Asia/Dacca", "Asia/Katmandu", "Asia/Macao", "Asia/Rangoon", "Asia/Saigon",
	"Asia/Thimbu", "Asia/Ujung_Pandang", "Asia/Ulan_Bator",
	"Europe/Kiev", "Europe/Uzhgorod", "Europe/Zaporozhye",
	"America/Buenos_Aires", "US/Eastern", "US/Pacific",
}

func main() {
	links, err := readLinks(filepath.Join(zoneDir, "tzdata.zi"))
	if err != nil {
		fail("读取 tzdata.zi: %v", err)
	}

	var problems []string
	missing := 0
	for alias, target := range links {
		if !exists(alias) {
			missing++
		}
		if p := compare(alias, target); p != "" {
			problems = append(problems, p)
		}
	}
	for _, alias := range required {
		if _, ok := links[alias]; !ok {
			problems = append(problems, "必需别名不在 tzdata.zi 中: "+alias)
		}
	}

	fmt.Printf("tz-verify: 别名 %d 个已校验（系统缺失 %d 个），问题 %d 个\n", len(links), missing, len(problems))
	for _, p := range problems {
		fmt.Println("  FAIL", p)
	}
	if len(problems) > 0 || len(links) == 0 {
		os.Exit(1)
	}
}

// readLinks 解析 tzdata.zi 中的 "L 目标 别名" 行。
func readLinks(path string) (map[string]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	links := map[string]string{}
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		if fs := strings.Fields(sc.Text()); len(fs) == 3 && fs[0] == "L" {
			links[fs[2]] = fs[1]
		}
	}
	return links, sc.Err()
}

func exists(name string) bool {
	_, err := os.Stat(filepath.Join(zoneDir, name))
	return err == nil
}

func compare(alias, target string) string {
	a, err := time.LoadLocation(alias)
	if err != nil {
		return fmt.Sprintf("%s: %v", alias, err)
	}
	b, err := time.LoadLocation(target)
	if err != nil {
		return fmt.Sprintf("%s -> %s: 目标加载失败: %v", alias, target, err)
	}
	for t := time.Date(1970, 1, 1, 12, 0, 0, 0, time.UTC); t.Year() <= 2037; t = t.AddDate(0, 0, 14) {
		an, ao := t.In(a).Zone()
		bn, bo := t.In(b).Zone()
		if an != bn || ao != bo {
			return fmt.Sprintf("%s vs %s @ %s: %s%+d vs %s%+d", alias, target, t.Format("2006-01-02"), an, ao, bn, bo)
		}
	}
	return ""
}

func fail(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "tz-verify: "+format+"\n", args...)
	os.Exit(1)
}
