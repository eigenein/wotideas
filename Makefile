all: static/app.css

static/app.css: css/main.less
	cat css/normalize.css css/main.less | nodejs node_modules/less/bin/lessc - static/app.css
