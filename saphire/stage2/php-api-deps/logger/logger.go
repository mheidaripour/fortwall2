package logger

import (
	color "github.com/fatih/color"
)

type colorFunc func(format string, a ...interface{})

const (
	Debug = iota
	Info
	Notice
	Warning
	Error
	Critical
)

var Level int = Notice

var prefix = []string{
	"debu",
	"info",
	"noti",
	"warn",
	"erro",
	"crit",
}

var printFuncs = []func(string, ...interface{}){
	color.Cyan,
	color.White,
	color.Green,
	color.Yellow,
	color.Red,
	color.Magenta,
}

func Log(lvl int, msg string, args ...interface{}) {
	if lvl >= Level && lvl < len(printFuncs) {
		printFuncs[lvl](msg, args...)
	}
}
