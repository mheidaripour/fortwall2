package main

import (
	"fmt"
	"os"
	"php-syscalls/php-api-deps/db"
	//"sort"
)

//var syscallTable = make(map[string][]string)
//var includes = make(map[string][]string)

func main() {
	if len(os.Args) < 2 || len(os.Args) > 3 {
		fmt.Printf("Usage: ./build-filters DB \n")
		os.Exit(0)
	}
	names := false
	if len(os.Args) == 3 {
		names = true
	}

	// syscallCounts := make(map[string]int)
	// syscallCountsPerFile := make(map[string]int)

	dbpath := os.Args[1]

	Db, _ := db.OpenDb(dbpath)

	// fileList := gotree.New("Files")
	// files := Db.GetFiles()
	if names {
		syscalls := Db.GetSyscallNamesForFile()
		for k, v := range syscalls {
			fmt.Printf("%s", k)
			for _, vv := range v {
				fmt.Printf(" %s", vv)
			}
			fmt.Printf("\n")
		}
	} else {
		syscalls := Db.GetSyscallIdsForFile()
		for k, v := range syscalls {
			fmt.Printf("%s", k)
			for _, vv := range v {
				fmt.Printf(" %d", vv)
			}
			fmt.Printf("\n")
		}
	}
	// for _, f := range files {
	// 	// fileTree := gotree.New(f)
	// 	fmt.Printf("%s", f)

	// 	// for _, scV := range syscalls {
	// 	// 	// syscallTree := gotree.New(scK)
	// 	// 	// for incK, incV := range scV {
	// 	// 	// 	// includeTree := gotree.New(incK)
	// 	// 	// 	for _, fnV := range incV {
	// 	// 	// 		includeTree.Add(fnV + "()")
	// 	// 	// 	}
	// 	// 	// 	// syscallTree.AddTree(includeTree)
	// 	// 	// }
	// 	// 	// fileTree.AddTree(syscallTree)
	// 	// 	// if _, ok := syscallCounts[scK]; !ok {
	// 	// 	// 	syscallCounts[scK] = 0
	// 	// 	// }
	// 	// 	// syscallCounts[scK] += 1
	// 	// 	fmt.Printf(" %d", scV)
	// 	// }
	// 	// fmt.Printf("\n")
	// 	// fileList.AddTree(fileTree)
	// }
	//fmt.Println(fileList.Print())
	// fmt.Printf("===\n")
	// for k, v := range syscallCounts {
	// 	fmt.Printf("%20s %-5d\n", k, v)
	// }
	// fmt.Printf("===\n")
	// for k, v := range syscallCountsPerFile {
	// 	fmt.Printf("%20s %-5d\n", k, v)
	// }
}
