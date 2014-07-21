all: static/app.css

static/app.css: css/main.less
	nodejs node_modules/less/bin/lessc css/main.less static/app.css
