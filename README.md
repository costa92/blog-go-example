# blog-go-example

[翼舞成梦博客](https://github.com/costa92/hexo_blog)的文章配套 Go 案例代码。

## 仓库分工

- `costa92/hexo_blog`：博客正文、Hexo 主题、发布流程和写作 skill。
- `costa92/blog-go-example`：文章中的可运行 Go 案例及其测试、使用说明。

按文章主题组织示例；示例说明应链接对应文章，并写明运行方法与演示边界。本仓库不承载 Hexo 博客源码，也不发布博客网站。

## 案例

- [Super-agent 协调层](superagent/README.md)：基于 `kart-io/goagent v0.33.0`，包含任务分工、消息路由、可恢复 Worker 和 Outbox 通知重试；另提供 [GoAgent Harness CSV 编码执行案例](superagent/codingworker/README.md)。
- [encoding/json v1 与 v2 对比](jsonv2/README.md)：用测试断言两个版本的默认行为差异、迁移选项和基准，需要 Go 1.27。
