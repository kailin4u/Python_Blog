#!/usr/bin/env python3
# coding:utf-8

import re
import hashlib
import json
import logging
import os
import smtplib
import time
from email.header import Header
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr

from aiohttp import web
from markdown2 import markdown

from webframe import get, post, user2cookie, Page, filelist
from model import next_id, User, Blog, Comment, Category
from configloader import configs
from APIError import APIError, APIValueError, APIPermissionError, APIResourceNotFoundError

logging.basicConfig(level=logging.INFO)


@get('/')
async def index(request, *, page='1'):
    user = request.__user__
    cats = await Category.findAll(orderBy='created_at desc')
    page_index = Page.page2int(page)
    num = await Blog.findNumber('*') - 1    # 去掉__about__页面
    p = Page(num, page_index, item_page=configs.blog_item_page, page_show=configs.page_show)
    p.pagelist()
    if num == 0:
        blogs = []
    else:
        blogs = await Blog.findAll(where='title<>?', args=['__about__'], orderBy='created_at desc', limit=(p.offset, p.limit))
        for blog in blogs:
            blog.html_summary = markdown(blog.summary, extras=['code-friendly', 'fenced-code-blocks'])
    return {
        '__template__': 'index.html',
        'web_meta': configs.web_meta,
        'user': user,
        'cats': cats,
        'page': p,
        'blogs': blogs,
        'disqus': configs.use_disqus
    }


@get('/about')
async def about(request):
    user = request.__user__
    cats = await Category.findAll(orderBy='created_at desc')
    blog = await Blog.findAll(where='title=?', args=['__about__'])
    logging.info('blog: %s' % blog)
    blog[0].html_content = markdown(blog[0].content, extras=['code-friendly', 'fenced-code-blocks'])
    return {
        '__template__': 'about.html',
        'web_meta': configs.web_meta,
        'user': user,
        'cats': cats,
        'blog': blog[0],
    }


@get('/signup')
async def signin():
    cats = await Category.findAll(orderBy='created_at desc')
    return {
        '__template__': 'signup.html',
        'web_meta': configs.web_meta,
        'cats': cats
    }


@get('/login')
async def login():
    cats = await Category.findAll(orderBy='created_at desc')
    return {
        '__template__': 'login.html',
        'web_meta': configs.web_meta,
        'cats': cats
    }


@get('/logout')
async def logout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.del_cookie(configs.cookie.name)
    logging.info('user logged out.')
    return r


@get('/blog/{id}')
async def get_blog(id, request):
    user = request.__user__
    cats = await Category.findAll(orderBy='created_at desc')
    blog = await Blog.find(id)
    blog.view_count = blog.view_count + 1
    await blog.update()
    comments = await Comment.findAll(where='blog_id=?', args=[id], orderBy='created_at desc')
    for c in comments:
        c.html_content = markdown(c.content, extras=['code-friendly', 'fenced-code-blocks'])
    blog.html_content = markdown(blog.content, extras=['code-friendly', 'fenced-code-blocks'])
    return {
        '__template__': 'blog.html',
        'web_meta': configs.web_meta,
        'user': user,
        'cats': cats,
        'blog': blog,
        'comments': comments,
        'disqus': configs.use_disqus
    }


@get('/user/{id}')
async def get_user(id, request):
    user = request.__user__
    cats = await Category.findAll(orderBy='created_at desc')
    user_show = await User.find(id)
    user_show.password = '******'
    return {
        '__template__': 'user.html',
        'web_meta': configs.web_meta,
        'user': user,
        'cats': cats,
        'user_show': user_show
    }


@get('/category/{id}')
async def get_category(id, request, *, page='1'):
    user = request.__user__
    cats = await Category.findAll(orderBy='created_at desc')
    category = await Category.find(id)
    page_index = Page.page2int(page)
    num = await Blog.findNumber('*', 'cat_id=?', [id])
    p = Page(num, page_index, item_page=configs.blog_item_page, page_show=configs.page_show)
    p.pagelist()
    if num == 0:
        blogs = []
    else:
        blogs = await Blog.findAll(where='cat_id=?', args=[id], orderBy='created_at desc', limit=(p.offset, p.limit))
        for blog in blogs:
            blog.html_summary = markdown(blog.summary, extras=['code-friendly', 'fenced-code-blocks'])
    return {
        '__template__': 'category.html',
        'web_meta': configs.web_meta,
        'user': user,
        'cats': cats,
        'page': p,
        'category': category,
        'blogs': blogs,
        'disqus': configs.use_disqus
    }


@get('/api/blog/{id}')
async def api_blog(*, id):
    blog = await Blog.find(id)
    return blog


# handler带有默认值的命名关键字参数，用来处理带有查询字符串的url
@get('/api/manage/blog')
async def api_manage_blog(*, page='1'):
    page_index = Page.page2int(page)
    num = await Blog.findNumber('*')
    p = Page(num, page_index, item_page=configs.manage_item_page, page_show=configs.page_show)
    if num == 0:
        return dict(page=p, blogs=())
    col = ['id', 'user_id', 'user_name', 'title', 'created_at']
    blogs = await Blog.findAll(col=col, orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)


# handler带有默认值的命名关键字参数，用来处理带有查询字符串的url
@get('/api/manage/comment')
async def api_manage_comment(*, page='1'):
    page_index = Page.page2int(page)
    num = await Comment.findNumber('*')
    p = Page(num, page_index, item_page=configs.manage_item_page, page_show=configs.page_show)
    if num == 0:
        return dict(page=p, comments=())
    comments = await Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=comments)


# handler带有默认值的命名关键字参数，用来处理带有查询字符串的url
@get('/api/manage/user')
async def api_manage_user(*, page='1'):
    page_index = Page.page2int(page)
    num = await User.findNumber('*')
    p = Page(num, page_index, item_page=configs.manage_item_page, page_show=configs.page_show)
    if num == 0:
        return dict(page=p, user=())
    users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    for u in users:
        u.password = '******'
    return dict(page=p, users=users)


# handler带有默认值的命名关键字参数，用来处理带有查询字符串的url
@get('/api/manage/category')
async def api_manage_category(*, page='1'):
    page_index = Page.page2int(page)
    num = await Category.findNumber('*')
    p = Page(num, page_index, item_page=configs.manage_item_page, page_show=configs.page_show)
    if num == 0:
        return dict(page=p, categories=())
    categories = await Category.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, categories=categories)


@get('/api/category/{id}')
async def api_category(*, id):
    cat = await Category.find(id)
    return cat


@get('/manage')
async def manage_ajax(request, *, page='1'):
    user = request.__user__
    cats = await Category.findAll(orderBy='created_at desc')
    # 设置Page类缺省值
    p = Page(1, 1, item_page=configs.manage_item_page, page_show=configs.page_show)
    return {
        '__template__': 'manage.html',
        'web_meta': configs.web_meta,
        'user': user,
        'cats': cats,
        'page': p
    }


@get('/manage/blog/create')
async def manage_blog_create(request):
    user = request.__user__
    cats = await Category.findAll(orderBy='created_at desc')
    return {
        '__template__': 'manage_blog_edit.html',
        'web_meta': configs.web_meta,
        'user': user,
        'cats': cats,
        'id': '',
        'action': '/api/create_blog'
    }


@get('/manage/blog/edit')
async def manage_blog_edit(request, *, id):
    user = request.__user__
    cats = await Category.findAll(orderBy='created_at desc')

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/upload')
    uploadlist = filelist(path)
    return {
        '__template__': 'manage_blog_edit.html',
        'web_meta': configs.web_meta,
        'user': user,
        'cats': cats,
        'id': id,
        'action': '/api/blog/%s' % id,
        'uploadlist': uploadlist
    }


@get('/manage/category/create')
async def manage_category_create(request):
    user = request.__user__
    cats = await Category.findAll(orderBy='created_at desc')
    return {
        '__template__': 'manage_category_edit.html',
        'web_meta': configs.web_meta,
        'user': user,
        'cats': cats,
        'id': '',
        'action': '/api/create_category'
    }


@get('/manage/category/edit')
async def manage_category_edit(request, *, id):
    user = request.__user__
    cats = await Category.findAll(orderBy='created_at desc')
    return {
        '__template__': 'manage_category_edit.html',
        'web_meta': configs.web_meta,
        'user': user,
        'cats': cats,
        'id': id,
        'action': '/api/category/%s' % id
    }


def _format_addr(s):
    name, addr = parseaddr(s)
    return formataddr((Header(name, 'utf-8').encode(), addr))


@get('/api/reset_password')
async def api_reset_password(*, email):
    # 重置密码
    if not email:
        raise APIValueError('email', 'Invalid email.')
    users = await User.findAll(where='email=?', args=[email])
    if len(users) == 0:
        raise APIValueError('email', 'Email not exist.')
    user = users[0]
    s = '%s:%d' % (user.id, int(time.time() * 1000))
    password0 = hashlib.md5(s.encode('utf-8')).hexdigest()[:10]        # 重置后的密码
    password1 = '%s:%s' % (email, password0)
    password1 = hashlib.sha1(password1.encode('utf-8')).hexdigest()    # 模拟客户端用email加密密码
    sha1_password = '%s:%s' % (user.id, password1)
    user.password = hashlib.sha1(sha1_password.encode('utf-8')).hexdigest()
    await user.update()

    # 发送email
    from_addr = configs.email.addr
    password = configs.email.password
    to_addr = email
    smtp_server = configs.email.server
    smtp_port = configs.email.port
    msg = MIMEText('您的密码已经重置，请使用新密码登陆网站并尽快修改密码。\n重置后的新密码为: ' + password0, 'plain', 'utf-8')
    msg['From'] = _format_addr('管理员 <%s>' % from_addr)
    msg['To'] = _format_addr('%s <%s>' % (user.name, to_addr))
    msg['Subject'] = Header('来自 ' + configs.web_meta.web_name + ' - 重置密码', 'utf-8').encode()
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.set_debuglevel(1)
    server.login(from_addr, password)
    server.sendmail(from_addr, [to_addr], msg.as_string())
    server.quit()
    return dict(email=email)

RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')


@post('/api/signup')
async def api_signin(*, email, name, password):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not RE_EMAIL.match(email):
        raise APIValueError('email')
    if not password or not RE_SHA1.match(password):
        raise APIValueError('password')

    users = await User.findAll(where='email=?', args=[email])
    if len(users) > 0:
        raise APIError('signup:failed', 'email', 'Email is already in use.')
    uid = next_id()
    sha1_password = '%s:%s' % (uid, password)
    user = User(id=uid, name=name.strip(), email=email, password=hashlib.sha1(sha1_password.encode('utf-8')).hexdigest(), image=configs.web_meta.user_image)
    await user.save()
    # 设置cookie
    r = web.Response()
    r.set_cookie(configs.cookie.name, user2cookie(user, configs.cookie.max_age), max_age=configs.cookie.max_age, httponly=True)
    user.password = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@post('/api/login')
async def api_login(*, email, password, rememberme):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    if not password:
        raise APIValueError('password', 'Invalid password.')
    users = await User.findAll(where='email=?', args=[email])
    if len(users) == 0:
        raise APIValueError('email', 'Email not exist.')
    user = users[0]
    # 检查密码
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(password.encode('utf-8'))
    logging.info('password:%s' % user.password)
    logging.info('sha1:%s' % sha1.hexdigest())
    if user.password != sha1.hexdigest():
        raise APIValueError('password', 'Invalid password.')
    # 密码正确，设置cookie
    r = web.Response()
    if rememberme:
        max_age = configs.cookie.max_age_long
    else:
        max_age = configs.cookie.max_age
    r.set_cookie(configs.cookie.name, user2cookie(user, max_age), max_age=max_age, httponly=True)
    user.password = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@post('/api/create_blog')
async def api_create_blog(request, *, title, summary, content, cat_name):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError('Only admin can do this!')
    if not title or not title.strip():
        raise APIValueError('title', 'Title can not be empty.')
    if not summary or not summary.strip():
        summary = content.strip()[:200]
    elif len(summary.strip()) > 200:
        raise APIValueError('summary', 'Length of summary can not be larger than 200.')
    if not content or not content.strip():
        raise APIValueError('content', 'Content can not be empty.')
    if not cat_name.strip():
        cat_id = None
    else:
        cats = await Category.findAll(where='name=?', args=[cat_name.strip()])
        if (len(cats) == 0):
            raise APIValueError('cat_name', 'cat_name is not belong to Category.')
        cat_id = cats[0].id
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, title=title.strip(), summary=summary.strip(), content=content.strip(), cat_id=cat_id, cat_name=cat_name.strip())
    await blog.save()
    return blog


@post('/api/blog/{id}')
async def api_update_blog(id, request, *, title, summary, content, cat_name):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError('Only admin can do this!')
    if not title or not title.strip():
        raise APIValueError('title', 'Title can not be empty.')
    if not summary or not summary.strip():
        summary = content.strip()[:200]
    elif len(summary.strip()) > 200:
        raise APIValueError('summary', 'Length of summary can not be larger than 200.')
    if not content or not content.strip():
        raise APIValueError('content', 'Content can not be empty.')
    blog = await Blog.find(id)
    blog.title = title.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    if not cat_name or not cat_name.strip():
        blog.cat_name = None
        blog.cat_id = None
    else:
        blog.cat_name = cat_name.strip()
        cats = await Category.findAll(where='name=?', args=[cat_name.strip()])
        if (len(cats) == 0):
            raise APIValueError('cat_name', 'cat_name is not belong to Category.')
        blog.cat_id = cats[0].id
    await blog.update()
    return blog


@post('/api/blog/{id}/delete')
async def api_delete_blog(request, *, id):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError('Only admin can do this!')
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    await blog.remove()
    return dict(id=id)


@post('/api/blog/{id}/comment')
async def api_create_comment(id, request, *, content):
    user = request.__user__
    if user is None:
        raise APIPermissionError('plz login befor comment!')
    if not content or not content.strip():
        raise APIValueError('comment', 'Comment can not be empty.')
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image, content=content.strip())
    await comment.save()
    return comment


@post('/api/comment/{id}/delete')
async def api_delete_comment(id, request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError('Only admin can do this!')
    comment = await Comment.find(id)
    if comment is None:
        raise APIResourceNotFoundError('Comment')
    await comment.remove()
    return dict(id=id)


@post('/api/user/{id}/delete')
async def api_delete_user(id, request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError('Only admin can do this!')
    user = await User.find(id)
    if user is None:
        raise APIResourceNotFoundError('User')
    await user.remove()
    return dict(id=id)


@post('/upload')
async def upload(request, *, file):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError('Only admin can do this!')
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    filename = path + '/upload/' + file.filename
    ext = os.path.splitext(filename)
    # 处理重名文件
    n = 1
    while os.path.exists(filename):
        filename = '%s~%d%s' % (ext[0], n, ext[1])
        n = n + 1

    with open(filename, 'wb') as f:
        f.write(file.file.read())
    return dict(filename=os.path.basename(filename))


@post('/api/create_category')
async def api_create_category(request, *, name):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError('Only admin can do this!')
    if not name or not name.strip():
        raise APIValueError('name', 'Name can not be empty.')
    cat = Category(name=name.strip())
    await cat.save()
    return cat


@post('/api/category/{id}')
async def api_update_category(id, request, *, name):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError('Only admin can do this!')
    if not name or not name.strip():
        raise APIValueError('name', 'Name can not be empty.')
    cat = await Category.find(id)
    cat.name = name.strip()
    await cat.update()
    return cat


@post('/api/category/{id}/delete')
async def api_delete_category(id, request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError('Only admin can do this!')
    cat = await Category.find(id)
    if cat is None:
        raise APIResourceNotFoundError('Category')
    await cat.remove()
    return dict(id=id)


@post('/api/preview')
async def api_preview(*, content):
    preview = markdown(content, extras=['code-friendly', 'fenced-code-blocks'])
    return dict(preview=preview)


@post('/api/modify_password')
async def api_modify_password(request, *, user_id, password0, password1, password2):
    if request.__user__ is None:
        raise APIPermissionError('You must login first!')
    if not user_id or not user_id.strip():
        raise APIValueError('user_id', 'user_id can not be empty.')
    if not password0 or not password0.strip():
        raise APIValueError('password0', 'old password can not be empty.')
    if not password1 or not RE_SHA1.match(password1):
        raise APIValueError('password1', 'Invalid new password.')
    if not password2 or not RE_SHA1.match(password2):
        raise APIValueError('password2', 'Invalid confirmimg password.')

    user = await User.find(user_id)
    if user is None:
        raise APIResourceNotFoundError('User not found')
    # 检查密码
    sha1 = hashlib.sha1()
    sha1.update(user_id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(password0.encode('utf-8'))
    if user.password != sha1.hexdigest():
        raise APIValueError('password', 'Invalid old password.')
    # 修改密码
    sha1_password = '%s:%s' % (user_id, password1)
    user.password = hashlib.sha1(sha1_password.encode('utf-8')).hexdigest()
    await user.update()
    return dict(user_id=user_id)
