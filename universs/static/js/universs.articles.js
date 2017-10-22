var active = null;

$(document).ready(function() {

    // Bind some key events
    $(document).keydown(function() {
        if (event.keyCode == 74) {
            // "J" key
            showNext();
        }
        else if (event.keyCode == 75) {
            // "K" key
            showPrevious();
        }
        else if (event.keyCode == 65) {
            // "A" key
            showAll();
        }
        else if (event.keyCode == 85) {
            // "U" key
            showUnread();
        }
        else if (event.keyCode == 67) {
            // "C" key
            toogleCollapse();
        }
        else if (event.keyCode == 82) {
            // "R" key
            toogleRead();
        }
        else if (event.keyCode == 77) {
            // "M" key
            toogleMark();
        }
        else if (event.keyCode == 83) {
            // "S" key
            toogleStar();
        }
        else if (event.keyCode == 79) {
            // "O" key
            openCurrentLink();
        }
    });

    // Mark articles as read when uncollapse
    $(".collapse").on('shown.bs.collapse', function(e) {
        // Get the article ID
        var id = $(e.target).data('bs.collapse').$trigger[0].hash.substring(1);
        // Set the new element as active element (globally)
        active = $("div#" + id);
        // Uncomment the content
        $(active).uncomment()
        // Mark the article as read
        read(id);
    });

    // Initialize the active article with the first article in the list
    // if (active == null) {
        // active = $("div#feed-articles ul li").first().next();
    // }

});

function showAll(id) {
    var url = window.location.origin + window.location.pathname;
    var parameters = window.location.search;
    var parameters = parameters.replace(/unread&?/, '').replace(/read&?/, '')
    var parameters = parameters.replace(/all&?/, '');
    // Remove trailing ampersand
    var parameters = parameters.replace(/&$/, '');
    if (!parameters.startsWith("?")) {
        var parameters = '?' + parameters;
    }
    window.location.replace(url + parameters + '&all');
}

function showUnread(id) {
    var url = window.location.origin + window.location.pathname;
    var parameters = window.location.search;
    var parameters = parameters.replace(/all&?/, '').replace(/read&?/, '')
    var parameters = parameters.replace(/unread&?/, '');
    // Remove trailing ampersand
    var parameters = parameters.replace(/&$/, '');
    if (!parameters.startsWith("?")) {
        var parameters = '?' + parameters;
    }
    window.location.replace(url + parameters + '&unread');
}

function read(id) {
    var element = $('a[href="#' + id + '"]');
    if ($(element).hasClass("article-unread")) {
        $.get('/flag/read/' + id);
        $(element).removeClass("article-unread");
        $(element).addClass("article-read");
        $("li#" + id + "-unread-button").show();
        $("li#" + id + "-read-button").hide();
        console.log("Flagging " + id + " as read");
    }
}

function unread(id) {
    var element = $('a[href="#' + id + '"]');
    if ($(element).hasClass("article-read")) {
        $.get('/flag/unread/' + id);
        $(element).removeClass("article-read");
        $(element).addClass("article-unread");
        $("li#" + id + "-unread-button").hide();
        $("li#" + id + "-read-button").show();
        console.log("Flagging " + id + " as unread");
    }
}

function mark(id) {
    var element = $('a[href="#' + id + '"]');
    if ($(element).hasClass("article-unmarked")) {
        $.get('/flag/marked/' + id);
        $(element).removeClass("article-unmarked");
        $(element).addClass("article-marked");
        $("li#" + id + "-unmark-button").show();
        $("li#" + id + "-mark-button").hide();
        console.log("Flagging " + id + " as marked");
    }
}

function unmark(id) {
    var element = $('a[href="#' + id + '"]');
    if ($(element).hasClass("article-marked")) {
        $.get('/flag/unmarked/' + id);
        $(element).removeClass("article-marked");
        $(element).addClass("article-unmarked");
        $("li#" + id + "-unmark-button").hide();
        $("li#" + id + "-mark-button").show();
        console.log("Flagging " + id + " as unmarked");
    }
}

function star(id) {
    var element = $('a[href="#' + id + '"]');
    if ($(element).hasClass("article-unstarred")) {
        $.get('/flag/starred/' + id);
        $(element).removeClass("article-unstarred");
        $(element).addClass("article-starred");
        $("li#" + id + "-unstarred-button").show();
        $("li#" + id + "-starred-button").hide();
        console.log("Flagging " + id + " as starred");
    }
}

function unstar(id) {
    var element = $('a[href="#' + id + '"]');
    if ($(element).hasClass("article-starred")) {
        $.get('/flag/unstarred/' + id);
        $(element).removeClass("article-starred");
        $(element).addClass("article-unstarred");
        $("li#" + id + "-unstarred-button").hide();
        $("li#" + id + "-starred-button").show();
        console.log("Flagging " + id + " as unstarred");
    }
}

function showNext() {
    if (active) {
        var li = $(active).nextAll("li")[0];
        if (li == null) {
            // There is no previous article (i.e. we are at the top)
            return
        }
        active = $(li).next();
    } else {
        // First article in list
        active = $("div#feed-articles ul li").first().next();
        var li = $(active).prev("li")
    }
    $(li).find("a").focus();
    $(active).collapse();
    // Scroll to put the article to the top
    window.scrollTo(0, $(li).offset()["top"] - 80);
}

function showPrevious() {
    if (active) {
        var li = $(active).prevAll("li")[1];
        if (li == null) {
            // There is no next article (i.e. we are at the bottom)
            return
        }
        active = $(li).next();
    } else {
        // Last article in list
        active = $("div#feed-articles ul li").last().next();
        var li = $(active).prev("li")
    }
    $(li).find("a").focus();
    $(active).collapse();
    // Scroll to put the article to the top
    window.scrollTo(0, $(li).offset()["top"] - 80);
}

function toogleRead() {
    if (active) {
        var id = $(active).attr("id");
        var li = $(active).prev()
        var link = $(li).find('a[href="#' + id + '"]')
        if ($(link).hasClass("article-unread")) {
            read(id);
        }
        else {
            unread(id);
        }
    }
}

function toogleMark() {
    if (active) {
        var id = $(active).attr("id");
        var li = $(active).prev()
        var link = $(li).find('a[href="#' + id + '"]')
        if ($(link).hasClass("article-unmarked")) {
            mark(id);
        }
        else {
            unmark(id);
        }
    }
}

function toogleStar() {
    if (active) {
        var id = $(active).attr("id");
        var li = $(active).prev()
        var link = $(li).find('a[href="#' + id + '"]')
        if ($(link).hasClass("article-unstarred")) {
            star(id);
        }
        else {
            unstar(id);
        }
    }
}

function markAllAsRead() {
    var articles = $('div#feed-articles div.collapse');
    for (var i = 0; i < articles.length; i++) {
        read(articles[i].id);
    }
}

function openCurrentLink() {
    if (active) {
        var url = $(active).find("ol li a").attr("href");
        window.open(url);
    }
}

function toogleCollapse() {
    if (active) {
        $(active).collapse("toggle")
    }
}

function normalize() {
    $('div#feed-articles img').removeProp('align');
}
