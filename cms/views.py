from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login, logout
from django.db.models import Sum, Avg, Q, Count
from django.db import IntegrityError
from django.core.files.storage import FileSystemStorage
from django.core.paginator import Paginator
from django.conf import settings
from django.utils import timezone
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, TruncQuarter, TruncYear
import json, uuid
from datetime import date, datetime, timedelta
from groq import Groq
from .models import (
    Event,
    News,
    Attribute,
    CoreValue,
    NewsEdition,
    Feedback,
    AdminActivity,
    VisitorLog,
    EventCoreValue,
    EventRegistration,
    Attendance,
)
from .recommendation import (get_recommended_events, get_latest_news)
from .sentiment import sentiment_analyzer
from .forms import EventRegistrationForm


# =====================
# ADMIN AUTH HELPER
# =====================
def admin_login_required(view_func):
    """Decorator: redirect ke login page kalau belum login sebagai admin."""
    def wrapper(request, *args, **kwargs):
        if not request.session.get('is_admin'):
            return redirect('admin_login')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# =====================
# ADMIN LOGIN / LOGOUT
# =====================
def admin_login_view(request):
    if request.session.get('is_admin'):
        return redirect('admin_home')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=username, password=password)

        if user is not None and (user.is_staff or user.is_superuser):
            login(request, user)
            request.session['is_admin'] = True
            request.session['admin_username'] = user.username
            return redirect('admin_home')
        else:
            error = 'Username atau password salah, atau akun tidak memiliki akses admin.'

    return render(request, 'cms/admin_login.html', {'error': error})


# Single canonical admin_login (used by url 'admin_login')
def admin_login(request):
    if request.session.get('is_admin'):
        return redirect('admin_home')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=username, password=password)
        if user is not None and (user.is_staff or user.is_superuser):
            login(request, user)
            request.session['is_admin'] = True
            request.session['admin_username'] = user.username
            return redirect('admin_home')
        # Fallback hardcoded (dev only)
        elif username == 'Admin' and password == '1234':
            request.session['is_admin'] = True
            request.session.save()
            return redirect('admin_home')
        else:
            error = 'Username atau password salah.'
    return render(request, 'cms/admin_login.html', {'error': error})


def admin_logout_view(request):
    request.session.flush()
    logout(request)
    return redirect('home')


def admin_logout(request):
    request.session.flush()
    return redirect('admin_login')


# =====================
# USER PAGES
# =====================
def home(request):
    VisitorLog.objects.create(
        page_visited='home',
        visit_duration=10,
        engagement_score=0.8,
    )

    avg_score = VisitorLog.objects.aggregate(
        avg=Avg('engagement_score')
    )['avg'] or 0
    engagement_score = round(float(avg_score) * 100)

    context = {
        # Only count Published events in public stats
        "total_events": Event.objects.filter(status=Event.STATUS_PUBLISHED).count(),
        "total_news": News.objects.count(),
        "total_attributes": Attribute.objects.count(),
        "core_values": CoreValue.objects.all(),
        "recommended_events": get_recommended_events(),
        "latest_news": get_latest_news(),
        "engagement_score": engagement_score,
    }

    return render(request, "cms/home.html", context)


def get_recommended_events(core_name=None):
    qs = Event.objects.filter(status=Event.STATUS_PUBLISHED)
    if core_name:
        qs = qs.filter(core_values__core_value_name=core_name)
    return qs.distinct()


def _recommended_items_for_core_slug(core_slug):
    if not core_slug:
        return []

    core_value = CoreValue.objects.filter(
        core_value_name__iexact=core_slug.replace("-", " ")
    ).first()
    if not core_value:
        return []

    event_ids = EventCoreValue.objects.filter(
        core_value=core_value
    ).values_list("event_id", flat=True)

    events = Event.objects.filter(
        event_id__in=event_ids,
        status=Event.STATUS_PUBLISHED
    ).order_by("-created_at")[:12]

    return [
        {
            "id": e.event_id,
            "title": e.event_name,
            "summary": (e.description or "")[:120],
            "image_url": e.image_url or "",
            "location": e.location or "",
            "event_date": str(e.event_date) if e.event_date else "",
            "rating": float(e.rating) if e.rating is not None else None,
            "category": core_value.core_value_name,
        }
        for e in events
    ]


def recommended_content(request):
    core_slug = (request.GET.get("core") or "").strip()
    return JsonResponse({"items": _recommended_items_for_core_slug(core_slug)})


def get_or_create_session(request):
    session_id = request.COOKIES.get('feedback_session')
    if not session_id:
        session_id = str(uuid.uuid4())
    return session_id


BULAN = {
    'januari': 1, 'februari': 2, 'maret': 3, 'april': 4,
    'mei': 5, 'juni': 6, 'juli': 7, 'agustus': 8,
    'september': 9, 'oktober': 10, 'november': 11, 'desember': 12
}

def parse_edition_date(edition):
    name = edition.edition_name.lower().strip()
    return BULAN.get(name, 0)


def explore(request):
    VisitorLog.objects.create(
        page_visited='explore',
        visit_duration=0,
        engagement_score=0.5,
    )

    session_id = get_or_create_session(request)

    # Business Rule: Only Published events show on Explore
    events = Event.objects.filter(
        status=Event.STATUS_PUBLISHED
    ).order_by('-event_date')

    for event in events:
        avg_rating = Feedback.objects.filter(
            event=event,
            rating__isnull=False
        ).aggregate(avg=Avg('rating'))['avg']

        if avg_rating:
            event.rating = round(avg_rating, 1)
        else:
            event.rating = None

    rated_events = Feedback.objects.filter(
        session_id=session_id,
        rating__isnull=False
    ).values_list('event_id', flat=True)

    news_editions = sorted(
        NewsEdition.objects.prefetch_related('news').all(),
        key=parse_edition_date,
        reverse=True
    )

    playbooks = Attribute.objects.filter(attribute_type='playbook')
    posters   = Attribute.objects.filter(attribute_type='poster')
    assets    = Attribute.objects.filter(attribute_type='asset')
    logos     = Attribute.objects.filter(attribute_type='logo')
    videos    = Attribute.objects.filter(attribute_type='video')

    context = {
        'events': events,
        'news_editions': news_editions,
        'playbooks': playbooks,
        'posters': posters,
        'assets': assets,
        'logos': logos,
        'videos': videos,
        'today': date.today(),
        'rated_events': rated_events,
    }

    response = render(request, 'cms/explore.html', context)
    response.set_cookie(
        'feedback_session', session_id,
        max_age=60 * 60 * 24 * 30,
        httponly=True, samesite='Lax'
    )
    return response


def feedback(request):
    return render(request, 'cms/feedback.html')


def classify_feedback(message):
    try:
        sentiment, confidence = sentiment_analyzer.predict(message)
    except Exception:
        sentiment = 'neutral'
        confidence = 0.50
    return sentiment, confidence

# =========================================================
# CHAT AI
# =========================================================
@require_http_methods(["POST"])
def chat_with_ai(request):

    try:
        data = json.loads(request.body)

        message  = data.get('message', '').strip()
        event_id = data.get('event_id')

        # ================= VALIDASI =================

        if not message:
            return JsonResponse({
                'status': 'error',
                'message': 'Pesan kosong'
            }, status=400)

        # ================= OPTIONAL EVENT =================
        # event boleh kosong
        event = None

        if event_id:
            try:
                event = Event.objects.get(event_id=event_id)

            except Event.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Event tidak valid'
                }, status=404)

        session_id = get_or_create_session(request)

        sentiment, confidence = classify_feedback(message)

        # ================= HISTORY CHAT =================

        previous_feedbacks = Feedback.objects.filter(
            session_id=session_id
        ).exclude(
            ai_response__isnull=True
        ).order_by('-created_at')[:5]

        previous_feedbacks = reversed(previous_feedbacks)

        # ================= CONTEXT DATA (EVENTS & NEWS) =================
        db_events = Event.objects.all().order_by('-event_date')[:5]
        db_news = News.objects.all().order_by('-created_at')[:5]

        events_list = []
        for ev in db_events:
            date_str = ev.event_date.strftime('%d %b %Y') if ev.event_date else 'Tidak ditentukan'
            time_str = ev.event_time.strftime('%H:%M') if ev.event_time else 'Tidak ditentukan'
            desc_str = ev.description[:120] + '...' if ev.description and len(ev.description) > 120 else (ev.description or '')
            events_list.append(
                f"- ID: {ev.event_id}\n"
                f"  Nama: {ev.event_name}\n"
                f"  Tanggal: {date_str}\n"
                f"  Waktu: {time_str}\n"
                f"  Lokasi: {ev.location or 'Tidak ditentukan'}\n"
                f"  Deskripsi: {desc_str}\n"
                f"  Link: /event_detail/{ev.event_id}/"
            )

        news_list = []
        for nw in db_news:
            date_str = nw.created_at.strftime('%d %b %Y') if nw.created_at else 'Tidak ditentukan'
            content_str = nw.content[:120] + '...' if nw.content and len(nw.content) > 120 else (nw.content or '')
            news_list.append(
                f"- ID: {nw.news_id}\n"
                f"  Judul: {nw.title or 'Tanpa Judul'}\n"
                f"  Tanggal: {date_str}\n"
                f"  Ringkasan: {content_str}\n"
                f"  Link: /news_redirect/{nw.news_id}/"
            )

        events_context_str = "\n\n".join(events_list) if events_list else "Tidak ada data event."
        news_context_str = "\n\n".join(news_list) if news_list else "Tidak ada data berita."

        current_event_context = ""
        if event:
            current_event_context = (
                f"User saat ini sedang membuka halaman event berikut:\n"
                f"- Nama: {event.event_name}\n"
                f"- Deskripsi: {event.description or 'Tidak ada'}\n"
                f"- Tanggal: {event.event_date.strftime('%d %b %Y') if event.event_date else 'Tidak ditentukan'}\n"
                f"- Lokasi: {event.location or 'Tidak ada'}\n\n"
            )

        # ================= PROMPT =================

        system_content = (
            "Kamu adalah asisten digital Pegadaian bernama Digi.\n\n"

            "Kamu HANYA boleh menjawab topik terkait Pegadaian, seperti:\n"
            "- budaya digital Pegadaian\n"
            "- layanan Pegadaian\n"
            "- aplikasi dan teknologi Pegadaian\n"
            "- event atau seminar Pegadaian\n"
            "- berita atau news Pegadaian\n"
            "- transformasi digital Pegadaian\n"
            "- pengalaman pengguna terhadap Pegadaian\n\n"

            f"{current_event_context}"

            "Berikut adalah data event terbaru/mendatang dari database Pegadaian:\n"
            f"{events_context_str}\n\n"

            "Berikut adalah data berita/news terbaru dari database Pegadaian:\n"
            f"{news_context_str}\n\n"

            "Jika user bertanya di luar Pegadaian "
            "(contoh: politik, game, kesehatan, coding umum, hiburan), "
            "tolak dengan sopan dan arahkan kembali ke topik Pegadaian.\n\n"

            "Ketika menjawab pertanyaan tentang event atau berita/news:\n"
            "- Gunakan data di atas untuk memberikan informasi yang akurat.\n"
            "- Berikan detail tanggal, lokasi, dan penjelasan singkat jika ditanyakan.\n"
            "- Sertakan link dalam bentuk tag HTML <a> agar user bisa mengkliknya langsung di chat. FORMAT LINK:\n"
            "  <a href=\"/event_detail/ID_EVENT/\" style=\"color: #00A651; font-weight: bold; text-decoration: underline;\">Nama Event</a>\n"
            "  atau <a href=\"/news_redirect/ID_NEWS/\" style=\"color: #00A651; font-weight: bold; text-decoration: underline;\">Judul Berita</a>\n"
            "- Ganti ID_EVENT atau ID_NEWS dengan ID riil yang sesuai dari data di atas.\n"
            "- PENTING: Gunakan tag HTML <a> persis seperti contoh di atas (dengan inline style warna hijau #00A651 agar kontras dan tebal). Jangan gunakan markdown link seperti [Nama](/link).\n\n"

            "Gunakan bahasa yang sama dengan user.\n"
            "- Indonesia → jawab Indonesia\n"
            "- English → jawab English\n"
            "- Campur → jawab natural\n\n"

            "Aturan:\n"
            "- Maksimal 3 kalimat. Namun, jika kamu memberikan daftar/list event atau berita, batasan 3 kalimat boleh dilonggarkan agar kamu bisa menyusun daftar poin-poin yang rapi, informatif, dan jelas.\n"
            "- Jangan terlalu panjang\n"
            "- Jawaban harus nyambung dengan chat sebelumnya\n"
            "- Ramah dan profesional\n"
            "- Jangan mengulang jawaban yang sama\n"
            "- Gaya modern AI assistant\n"
            "- Jika user memberi kritik → respon empati\n"
            "- Jika user memberi pujian → respon positif singkat\n\n"

            "Di akhir jawaban tambahkan:\n"
            "IS_FEEDBACK:true\n"
            "jika user memberi opini, kritik, pengalaman, atau penilaian.\n\n"

            "IS_FEEDBACK:false\n"
            "jika user hanya bertanya informasi biasa."
        )

        messages = [
            {
                "role": "system",
                "content": system_content
            }
        ]

        # ================= HISTORY =================

        for fb in previous_feedbacks:

            messages.append({
                "role": "user",
                "content": fb.message
            })

            messages.append({
                "role": "assistant",
                "content": fb.ai_response
            })

        # ================= USER MESSAGE =================

        messages.append({
            "role": "user",
            "content": message
        })

        # ================= AI RESPONSE =================

        client = Groq(api_key=settings.GROQ_API_KEY)

        groq_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=300,
            temperature=0.6,
        )

        full_reply = groq_response.choices[0].message.content.strip()

        # ================= FEEDBACK FLAG =================

        is_feedback = False

        if "IS_FEEDBACK:true" in full_reply:
            is_feedback = True

        reply = (
            full_reply
            .replace("IS_FEEDBACK:true", "")
            .replace("IS_FEEDBACK:false", "")
            .strip()
        )

        # ================= SAVE DB =================

        fb = Feedback.objects.create(
            session_id=session_id,
            event=event,
            message=message,
            ai_response=reply,
            sentiment=sentiment,
            rating=None,
            source_platform='web',
        )

        # ================= CEK RATING =================

        show_rating = False

        # rating hanya muncul kalau:
        # 1. feedback
        # 2. ada event
        # 3. event sudah selesai
        if is_feedback and event:

            already_rated = Feedback.objects.filter(
                session_id=session_id,
                event=event,
                rating__isnull=False
            ).exists()

            show_rating = (
                event.event_date < date.today()
                and not already_rated
            )

        # ================= RESPONSE =================

        response = JsonResponse({
            'status': 'success',
            'reply': reply,
            'feedback_id': fb.feedback_id,
            'sentiment': sentiment,
            'confidence': round(confidence * 100),
            'show_rating': show_rating
        })

        response.set_cookie(
            'feedback_session',
            session_id,
            max_age=60*60*24*30,
            httponly=True,
            samesite='Lax'
        )

        return response

    except Exception as e:

        import traceback
        traceback.print_exc()

        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

# =========================================================
# SAVE RATING
# =========================================================

@require_http_methods(["POST"])
def save_feedback(request):

    try:
        data = json.loads(request.body)

        feedback_id = data.get('feedback_id')
        rating      = data.get('rating')

        if not feedback_id:
            return JsonResponse({
                'status': 'error',
                'message': 'Feedback ID tidak ditemukan'
            }, status=400)

        if not rating:
            return JsonResponse({
                'status': 'error',
                'message': 'Rating wajib diisi'
            }, status=400)

        rating = int(rating)

        if rating < 1 or rating > 5:
            return JsonResponse({
                'status': 'error',
                'message': 'Rating harus 1-5'
            }, status=400)

        session_id = get_or_create_session(request)

        fb = Feedback.objects.get(
            feedback_id=feedback_id
        )

        # ================= CEK SESSION =================
        if fb.session_id != session_id:
            return JsonResponse({
                'status': 'error',
                'message': 'Session tidak valid'
            }, status=403)

        # ================= CEK SUDAH RATING =================
        if fb.rating is not None:
            return JsonResponse({
                'status': 'error',
                'message': 'Rating sudah pernah diberikan'
            }, status=400)

        # ================= UPDATE RATING =================
        fb.rating = rating
        fb.save()

        # ================= UPDATE AVG EVENT =================
        avg_rating = Feedback.objects.filter(
            event=fb.event,
            rating__isnull=False
        ).aggregate(avg=Avg('rating'))['avg']

        fb.event.rating = round(avg_rating, 1)
        fb.event.save()

        return JsonResponse({
            'status': 'success',
            'message': 'Rating berhasil disimpan',
            'avg_rating': fb.event.rating
        })

    except Feedback.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Feedback tidak ditemukan'
        }, status=404)

    except Exception as e:
        import traceback
        traceback.print_exc()

        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


def culture_performance(request):
    return render(request, 'cms/culture_performance.html')


def business_performance(request):
    return render(request, 'cms/business_performance.html')


def detail(request, id):
    return render(request, 'cms/detail.html')


# =====================
# EVENT DETAIL
# =====================
def _get_participation_context(request, event):
    """
    Tentukan email peserta yang "sedang teridentifikasi" di browser ini
    (lewat session, hasil registrasi/attendance/cek-status sebelumnya),
    lalu hitung status partisipasinya untuk event ini.

    Mengembalikan dict siap pakai untuk context template:
        {
            'participant_email': str | None,
            'participation': {'code': str, 'label': str} | None,
            'is_already_registered': bool,
        }
    """
    email = (request.session.get('participant_email') or '').strip().lower()

    participation = None
    is_already_registered = False

    if email:
        reg = EventRegistration.objects.filter(
            event_id=event.event_id,
            email__iexact=email,
        ).first()
        if reg is not None:
            is_already_registered = True
            participation = reg.get_participation_status()

    return {
        'participant_email': email or None,
        'participation': participation,
        'is_already_registered': is_already_registered,
    }


def event_detail(request, id):
    event = get_object_or_404(Event, event_id=id)

    # Business Rule: Archived events only for admin
    if event.status == Event.STATUS_ARCHIVED:
        if not request.session.get('is_admin'):
            return redirect('explore')

    # Business Rule: Draft/Published only — participants can still see Completed
    if event.status == Event.STATUS_DRAFT:
        if not request.session.get('is_admin'):
            return redirect('explore')

    VisitorLog.objects.create(
        page_visited=f'event_detail/{id}',
        visit_duration=0,
        engagement_score=0.5,
        visitor_ip=request.META.get('REMOTE_ADDR', ''),
    )

    context = {'event': event}
    context.update(_get_participation_context(request, event))
    return render(request, 'cms/event_detail.html', context)


def check_participation_status(request, id):
    """
    Form kecil "Cek Status Pendaftaran": peserta mengetik email,
    sistem menyimpan email itu ke session (supaya halaman Event Detail
    bisa menampilkan status partisipasi tanpa perlu login), lalu
    redirect balik ke Event Detail.
    """
    event = get_object_or_404(Event, event_id=id)
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if request.method != "POST":
        return redirect('event_detail', id=event.event_id)

    # "Bukan saya / ganti email": hapus identitas peserta dari session.
    if request.POST.get('clear') == '1':
        request.session.pop('participant_email', None)
        if is_ajax:
            return JsonResponse({"status": "success", "cleared": True})
        return redirect('event_detail', id=event.event_id)

    email = (request.POST.get('email') or '').strip().lower()
    if not email:
        msg = "Email wajib diisi untuk mengecek status pendaftaran."
        if is_ajax:
            return JsonResponse({"status": "error", "errors": [msg]}, status=400)
        return redirect('event_detail', id=event.event_id)

    reg = EventRegistration.objects.filter(
        event_id=event.event_id,
        email__iexact=email,
    ).first()

    if reg is None:
        msg = "Email ini belum pernah mendaftar pada event ini."
        if is_ajax:
            return JsonResponse({"status": "error", "errors": [msg]}, status=404)
        return redirect('event_detail', id=event.event_id)

    # Simpan ke session supaya halaman ini (dan kunjungan berikutnya di
    # browser yang sama) otomatis tahu siapa peserta yang sedang melihat.
    request.session['participant_email'] = email

    if is_ajax:
        participation = reg.get_participation_status()
        return JsonResponse({
            "status": "success",
            "participation_code": participation['code'],
            "participation_label": participation['label'],
        })

    return redirect('event_detail', id=event.event_id)


def _format_event_date(event):
    if not event.event_date:
        return "-"
    months = [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember",
    ]
    d = event.event_date
    return f"{d.day} {months[d.month - 1]} {d.year}"


def register_event(request, id):
    event = get_object_or_404(Event, event_id=id)
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    # Business Rule: registration only for Published events within deadline
    if not event.is_registration_open:
        msg = "Registrasi untuk event ini sudah ditutup atau belum dibuka."
        if is_ajax:
            return JsonResponse({"status": "error", "errors": [msg]}, status=400)
        return render(request, "cms/event_detail.html", {"event": event, "errors": [msg]})

    # Check capacity
    if event.is_full:
        msg = "Kuota event ini sudah penuh."
        if is_ajax:
            return JsonResponse({"status": "error", "errors": [msg]}, status=400)
        return render(request, "cms/event_detail.html", {"event": event, "errors": [msg]})

    if request.method == "POST":
        data = request.POST.copy()
        if not data.get("full_name") and data.get("nama"):
            data["full_name"] = data.get("nama")
        if not data.get("organization") and data.get("instansi"):
            data["organization"] = data.get("instansi")

        # Validasi backend eksplisit: tolak kalau email ini SUDAH terdaftar
        # untuk event ini. Ini lapisan pertahanan tambahan di server —
        # tombol "Daftar" di frontend juga disembunyikan untuk peserta yang
        # sudah teridentifikasi terdaftar, tapi validasi ini tetap berjalan
        # di backend terlepas dari apa yang dikirim klien.
        submitted_email = (data.get("email") or "").strip().lower()
        if submitted_email:
            already_registered = EventRegistration.objects.filter(
                event_id=event.event_id,
                email__iexact=submitted_email,
            ).exists()
            if already_registered:
                errors = ["Email ini sudah terdaftar untuk event ini."]
                if is_ajax:
                    return JsonResponse({"status": "error", "errors": errors}, status=400)
                return render(
                    request, "cms/event_detail.html",
                    {"event": event, "errors": errors, "open_register_modal": True},
                )

        form = EventRegistrationForm(data, event=event)

        if not form.is_valid():
            errors = [msg for field_errors in form.errors.values() for msg in field_errors]
            if is_ajax:
                return JsonResponse({"status": "error", "errors": errors}, status=400)
            return render(
                request, "cms/event_detail.html",
                {"event": event, "errors": errors, "form": form, "open_register_modal": True},
            )

        reg = form.save(commit=False)
        reg.event_id = event.event_id
        reg.event_name = event.event_name
        try:
            reg.save()
        except IntegrityError:
            errors = ["Email ini sudah terdaftar untuk event ini."]
            if is_ajax:
                return JsonResponse({"status": "error", "errors": errors}, status=400)
            return render(
                request, "cms/event_detail.html",
                {"event": event, "errors": errors, "form": form, "open_register_modal": True},
            )

        # Simpan email ke session supaya halaman Event Detail langsung tahu
        # status partisipasi peserta ini begitu mereka kembali / refresh.
        request.session['participant_email'] = reg.email

        payload = {
            "status": "success",
            "event_name": event.event_name,
            "event_date": _format_event_date(event),
        }
        if is_ajax:
            return JsonResponse(payload)

        return render(
            request, "cms/event_detail.html",
            {"event": event, "show_success": True, **payload},
        )

    return redirect("event_detail", id=event.event_id)


def success_page(request):
    event_name = request.session.pop("last_registration_event", None)
    return render(request, "cms/success.html", {"event_name": event_name})


# =====================
# API
# =====================
def recommended_content_api(request):
    core_slug = (request.GET.get("core") or "").strip()
    return JsonResponse({"items": _recommended_items_for_core_slug(core_slug)})


@csrf_exempt
def track_activity(request):
    if request.method == "POST":
        data = json.loads(request.body)
        print("Activity:", data)
        return JsonResponse({"status": "tracked"})
    return JsonResponse({"status": "invalid"})


# =====================
# ADMIN PAGES (CUSTOM)
# =====================

def log_admin_activity(message):
    AdminActivity.objects.create(activity=message)


@admin_login_required
def admin_home(request):
    today = timezone.localdate()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.GET.get('action') == 'get_chart_data':
        def format_avg_time(avg_sec):
            if not avg_sec:
                return "0s"
            m = int(avg_sec // 60)
            s = int(avg_sec % 60)
            if m > 0:
                return f"{m}m {s}s"
            return f"{s}s"

        period = request.GET.get('period', '1week')
        labels = []
        data = []
        avg_times = []
        date_range_text = ""

        if period == '1week':
            start_date = today - timedelta(days=6)
            date_range_text = f"{start_date.strftime('%b %d %Y')} - {today.strftime('%b %d %Y')}"
            days = [start_date + timedelta(days=i) for i in range(7)]
            labels = [d.strftime('%d/%m') for d in days]
            qs = VisitorLog.objects.filter(visited_at__date__gte=start_date, visited_at__date__lte=today)
            agg = qs.annotate(period_val=TruncDay('visited_at')).values('period_val').annotate(
                count=Count('log_id'), avg_duration=Avg('visit_duration')
            )
            count_map = {}
            avg_map = {}
            for item in agg:
                if item['period_val']:
                    dt = timezone.localtime(item['period_val']).date() if timezone.is_aware(item['period_val']) else item['period_val'].date()
                    count_map[dt] = count_map.get(dt, 0) + item['count']
                    avg_map[dt] = item['avg_duration']
            for d in days:
                data.append(count_map.get(d, 0))
                avg_times.append(format_avg_time(avg_map.get(d, 0)))

        elif period == '1month':
            start_date = today - timedelta(days=29)
            date_range_text = f"{start_date.strftime('%b %d %Y')} - {today.strftime('%b %d %Y')}"
            days = [start_date + timedelta(days=i) for i in range(30)]
            labels = [d.strftime('%d/%m') for d in days]
            qs = VisitorLog.objects.filter(visited_at__date__gte=start_date, visited_at__date__lte=today)
            agg = qs.annotate(period_val=TruncDay('visited_at')).values('period_val').annotate(
                count=Count('log_id'), avg_duration=Avg('visit_duration')
            )
            count_map = {}
            avg_map = {}
            for item in agg:
                if item['period_val']:
                    dt = timezone.localtime(item['period_val']).date() if timezone.is_aware(item['period_val']) else item['period_val'].date()
                    count_map[dt] = count_map.get(dt, 0) + item['count']
                    avg_map[dt] = item['avg_duration']
            for d in days:
                data.append(count_map.get(d, 0))
                avg_times.append(format_avg_time(avg_map.get(d, 0)))

        elif period in ['6months', '1year']:
            months_count = 6 if period == '6months' else 12
            start_date = today.replace(day=1)
            for _ in range(months_count - 1):
                start_date = (start_date - timedelta(days=1)).replace(day=1)
            date_range_text = f"{start_date.strftime('%b %Y')} - {today.strftime('%b %Y')}"
            months_list = []
            curr = start_date
            for _ in range(months_count):
                months_list.append((curr.year, curr.month))
                curr = (curr.replace(day=28) + timedelta(days=4)).replace(day=1)
            labels = [date(m[0], m[1], 1).strftime('%b') for m in months_list]
            qs = VisitorLog.objects.filter(visited_at__date__gte=start_date, visited_at__date__lte=today)
            agg = qs.annotate(period_val=TruncMonth('visited_at')).values('period_val').annotate(
                count=Count('log_id'), avg_duration=Avg('visit_duration')
            )
            count_map = {}
            avg_map = {}
            for item in agg:
                if item['period_val']:
                    dt = timezone.localtime(item['period_val']).date() if timezone.is_aware(item['period_val']) else item['period_val'].date()
                    count_map[(dt.year, dt.month)] = count_map.get((dt.year, dt.month), 0) + item['count']
                    avg_map[(dt.year, dt.month)] = item['avg_duration']
            for m in months_list:
                data.append(count_map.get(m, 0))
                avg_times.append(format_avg_time(avg_map.get(m, 0)))

        return JsonResponse({
            'labels': labels, 'data': data,
            'avg_times': avg_times, 'date_range_text': date_range_text
        })

    start_date_initial = today - timedelta(days=6)
    initial_date_range_text = f"{start_date_initial.strftime('%b %d %Y')} - {today.strftime('%b %d %Y')}"
    days = [start_date_initial + timedelta(days=i) for i in range(7)]
    weekly_labels = [d.strftime('%d/%m') for d in days]

    def format_avg_time(avg_sec):
        if not avg_sec:
            return "0s"
        m = int(avg_sec // 60)
        s = int(avg_sec % 60)
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    qs_initial = VisitorLog.objects.filter(visited_at__date__gte=start_date_initial, visited_at__date__lte=today)
    agg_initial = qs_initial.annotate(period_val=TruncDay('visited_at')).values('period_val').annotate(
        count=Count('log_id'), avg_duration=Avg('visit_duration')
    )
    count_map_initial = {}
    avg_map_initial = {}
    for item in agg_initial:
        if item['period_val']:
            dt = timezone.localtime(item['period_val']).date() if timezone.is_aware(item['period_val']) else item['period_val'].date()
            count_map_initial[dt] = count_map_initial.get(dt, 0) + item['count']
            avg_map_initial[dt] = item['avg_duration']
    weekly_data = []
    weekly_avg_times = []
    for d in days:
        weekly_data.append(count_map_initial.get(d, 0))
        weekly_avg_times.append(format_avg_time(avg_map_initial.get(d, 0)))

    total_visits = VisitorLog.objects.count()
    avg_visit_seconds = VisitorLog.objects.aggregate(avg_duration=Avg('visit_duration'))['avg_duration'] or 0
    avg_time = f"{int(avg_visit_seconds // 60)}m {int(avg_visit_seconds % 60)}s"
    avg_engagement_score = VisitorLog.objects.aggregate(avg_engagement=Avg('engagement_score'))['avg_engagement'] or 0
    if avg_engagement_score >= 0.7:
        engagement_text = 'High'
    elif avg_engagement_score >= 0.4:
        engagement_text = 'Medium'
    else:
        engagement_text = 'Low'

    last_week_visits = VisitorLog.objects.filter(visited_at__date__gte=start_date_initial, visited_at__date__lte=today).count()
    previous_week_visits = VisitorLog.objects.filter(
        visited_at__date__gte=start_date_initial - timedelta(days=7),
        visited_at__date__lt=start_date_initial
    ).count()
    if previous_week_visits:
        trends = f"{round((last_week_visits - previous_week_visits) / previous_week_visits * 100)}%"
    else:
        trends = f"+{last_week_visits * 10}%" if last_week_visits else "0%"

    total_content = Event.objects.count() + News.objects.count() + Attribute.objects.count()
    total_views = VisitorLog.objects.count()
    active_content = Event.objects.filter(status__in=[Event.STATUS_PUBLISHED, Event.STATUS_ONGOING]).count()
    total_feedback = Feedback.objects.count()

    feedback_messages = [item.message for item in Feedback.objects.all()]
    common_words = sentiment_analyzer.extract_common_words(feedback_messages, limit=6)
    common_word_list = [{'word': word, 'count': count} for word, count in common_words]

    event_keywords = {
        'Culture Workshop 2026': ['culture', 'workshop', '2026'],
        'Team Building Day': ['team building', 'team', 'building'],
        'Leadership Seminar': ['leadership', 'seminar'],
    }
    event_ranking = []
    for event_name, keywords in event_keywords.items():
        query = None
        for keyword in keywords:
            q = Q(message__icontains=keyword)
            query = q if query is None else query | q
        if query is None:
            continue
        event_feedback = Feedback.objects.filter(query)
        total_event = event_feedback.count()
        positive_event = event_feedback.filter(sentiment='positive').count()
        negative_event = event_feedback.filter(sentiment='negative').count()
        if total_event:
            event_ranking.append({
                'event': event_name,
                'total': total_event,
                'positive': positive_event,
                'negative': negative_event,
                'score': round(positive_event / total_event * 100),
            })
    event_ranking.sort(key=lambda row: row['score'], reverse=True)
    event_ranking = event_ranking[:5]

    total_positive = Feedback.objects.filter(sentiment='positive').count()
    total_neutral = Feedback.objects.filter(sentiment='neutral').count()
    total_negative = Feedback.objects.filter(sentiment='negative').count()

    if total_feedback:
        positive_percent = round(total_positive / total_feedback * 100)
        neutral_percent = round(total_neutral / total_feedback * 100)
        negative_percent = round(total_negative / total_feedback * 100)
    else:
        positive_percent = neutral_percent = negative_percent = 0

    recent_admin_activities = list(AdminActivity.objects.all().order_by('-created_at')[:6])
    recent_feedbacks = list(Feedback.objects.order_by('-created_at')[:10])

    def format_activity_time(dt):
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        now = timezone.localtime(timezone.now())
        dt = timezone.localtime(dt)
        diff = now - dt
        seconds = diff.seconds
        if diff.days == 0:
            if seconds < 60:
                return f"{seconds}s ago"
            if seconds < 3600:
                return f"{seconds // 60}m ago"
            return f"Today {dt.strftime('%H:%M')}"
        if diff.days == 1:
            return f"Yesterday {dt.strftime('%H:%M')}"
        if diff.days < 7:
            return f"{diff.days} days ago"
        return dt.strftime('%d %b %Y %H:%M')

    recent_admin_activities_data = []
    for activity in reversed(recent_admin_activities):
        recent_admin_activities_data.append({
            'icon': '📝',
            'title': activity.activity,
            'when': format_activity_time(activity.created_at),
        })

    recent_feedbacks_data = []
    for fb in recent_feedbacks:
        preview = fb.message.strip().replace('\n', ' ')
        if len(preview) > 90:
            preview = preview[:90].rsplit(' ', 1)[0] + '...'
        recent_feedbacks_data.append({
            'comment': preview,
            'sentiment': fb.sentiment.capitalize(),
            'rating': fb.rating if fb.rating is not None else 'N/A',
            'platform': fb.source_platform.capitalize(),
            'when': format_activity_time(fb.created_at),
        })

    context = {
        'total_content': total_content,
        'total_views': total_views,
        'active_content': active_content,
        'total_feedback': total_feedback,
        'weekly_data': weekly_data,
        'weekly_avg_times_json': json.dumps(weekly_avg_times),
        'weekly_labels': weekly_labels,
        'weekly_data_json': json.dumps(weekly_data),
        'weekly_labels_json': json.dumps(weekly_labels),
        'initial_date_range_text': initial_date_range_text,
        'recent_admin_activities': recent_admin_activities_data,
        'recent_feedbacks': recent_feedbacks_data,
        'total_visits': total_visits,
        'avg_time': avg_time,
        'engagement_text': engagement_text,
        'trends': trends,
        'positive': total_positive,
        'neutral': total_neutral,
        'negative': total_negative,
        'positive_percent': positive_percent,
        'neutral_percent': neutral_percent,
        'negative_percent': negative_percent,
        'event_ranking': event_ranking,
    }
    return render(request, 'cms/admin.html', context)


@admin_login_required
def explore_admin(request):
    # Admin sees ALL events regardless of status
    events = Event.objects.all().order_by('-event_date')
    today = date.today()

    for event in events:
        event.views = VisitorLog.objects.filter(
            page_visited=f'event_detail/{event.event_id}'
        ).count()
        event.registrant_count = EventRegistration.objects.filter(event_id=event.event_id).count()

    news_items = News.objects.all().order_by('-created_at')
    for n in news_items:
        n.views = VisitorLog.objects.filter(page_visited=f'news_detail/{n.news_id}').count()
        last_view = VisitorLog.objects.filter(page_visited=f'news_detail/{n.news_id}').order_by('-visited_at').first()
        n.last_viewed = last_view.visited_at if last_view else None

    attributes = Attribute.objects.all().order_by('-created_at')
    for a in attributes:
        a.views = VisitorLog.objects.filter(page_visited=f'attribute_detail/{a.attribute_id}').count()
        last_view = VisitorLog.objects.filter(page_visited=f'attribute_detail/{a.attribute_id}').order_by('-visited_at').first()
        a.last_viewed = last_view.visited_at if last_view else None

    context = {
        'events': events,
        'news_items': news_items,
        'attributes': attributes,
        'status_choices': Event.STATUS_CHOICES,
    }
    return render(request, 'cms/explore_admin.html', context)


def redirect_news(request, id):
    news_item = get_object_or_404(News, news_id=id)
    VisitorLog.objects.create(
        page_visited=f'news_detail/{id}',
        visitor_ip=request.META.get('REMOTE_ADDR')
    )
    return redirect(news_item.image_url if news_item.image_url else '/explore/')


def redirect_attribute(request, id):
    attr = get_object_or_404(Attribute, attribute_id=id)
    VisitorLog.objects.create(
        page_visited=f'attribute_detail/{id}',
        visitor_ip=request.META.get('REMOTE_ADDR')
    )
    return redirect(attr.file_url if attr.file_url else '/explore/')


@admin_login_required
def admin_add_event(request):
    if request.method == 'POST':
        event_name  = request.POST.get('event_name', '').strip()
        description = request.POST.get('description', '').strip()
        location    = request.POST.get('location', '').strip()
        event_date  = request.POST.get('event_date')
        event_time  = request.POST.get('event_time')
        status      = request.POST.get('status', Event.STATUS_DRAFT)
        capacity    = request.POST.get('capacity') or None
        person_in_charge       = request.POST.get('person_in_charge', '').strip() or None
        registration_deadline  = request.POST.get('registration_deadline') or None
        attendance_open_time   = request.POST.get('attendance_open_time') or None
        attendance_close_time  = request.POST.get('attendance_close_time') or None

        image_file = request.FILES.get('image')
        image_path = None
        if image_file:
            fs = FileSystemStorage(location='media/events')
            filename = fs.save(image_file.name, image_file)
            image_path = f'events/{filename}'

        if event_name:
            Event.objects.create(
                event_name=event_name,
                description=description or None,
                location=location or None,
                event_date=date.fromisoformat(event_date) if event_date else None,
                event_time=event_time or None,
                image_url=image_path,
                status=status,
                capacity=int(capacity) if capacity else None,
                person_in_charge=person_in_charge,
                registration_deadline=registration_deadline,
                attendance_open_time=attendance_open_time,
                attendance_close_time=attendance_close_time,
            )
            log_admin_activity(f"Event '{event_name}' dibuat dengan status '{status}'")
            return redirect('admin_explore')

    return render(request, 'cms/event_form.html', {
        'action': 'Tambah Event',
        'event': None,
        'form_action': 'admin_add_event',
        'status_choices': Event.STATUS_CHOICES,
    })


@admin_login_required
def admin_edit_event(request, id):
    event = get_object_or_404(Event, event_id=id)
    if request.method == 'POST':
        old_name = event.event_name
        event.event_name   = request.POST.get('event_name', '').strip() or event.event_name
        event.description  = request.POST.get('description', '').strip() or event.description
        event.location     = request.POST.get('location', '').strip() or event.location
        event.status       = request.POST.get('status', event.status)
        event.person_in_charge = request.POST.get('person_in_charge', '').strip() or event.person_in_charge

        capacity = request.POST.get('capacity')
        event.capacity = int(capacity) if capacity else event.capacity

        reg_dl = request.POST.get('registration_deadline')
        att_open = request.POST.get('attendance_open_time')
        att_close = request.POST.get('attendance_close_time')
        if reg_dl:
            event.registration_deadline = reg_dl
        if att_open:
            event.attendance_open_time = att_open
        if att_close:
            event.attendance_close_time = att_close

        event_date = request.POST.get('event_date')
        event_time = request.POST.get('event_time')

        image_file = request.FILES.get('image')
        if image_file:
            fs = FileSystemStorage(location='media/events')
            filename = fs.save(image_file.name, image_file)
            event.image_url = f'events/{filename}'

        event.event_date = date.fromisoformat(event_date) if event_date else event.event_date
        event.event_time = event_time or event.event_time
        event.save()
        log_admin_activity(f"Event '{old_name}' diperbarui → '{event.event_name}' (status: {event.status})")
        return redirect('admin_explore')

    return render(request, 'cms/event_form.html', {
        'action': 'Edit Event',
        'event': event,
        'form_action': 'admin_edit_event',
        'status_choices': Event.STATUS_CHOICES,
    })


@admin_login_required
def admin_delete_event(request, id):
    if request.method == 'POST':
        event = get_object_or_404(Event, event_id=id)
        event_name = event.event_name
        event.delete()
        log_admin_activity(f"Event '{event_name}' dihapus")
    return redirect('admin_explore')


@admin_login_required
def admin_event_preview(request, id):
    event = get_object_or_404(Event, event_id=id)
    context = {'event': event, 'today': date.today()}
    return render(request, 'cms/admin_event_preview.html', context)


# ── Change status via AJAX / POST ───────────────────────────────
@admin_login_required
def admin_change_event_status(request, id):
    if request.method == 'POST':
        event = get_object_or_404(Event, event_id=id)
        new_status = request.POST.get('status') or json.loads(request.body or '{}').get('status')
        valid = [s[0] for s in Event.STATUS_CHOICES]
        if new_status in valid:
            old = event.status
            event.status = new_status
            event.save()
            log_admin_activity(f"Status event '{event.event_name}' diubah dari '{old}' ke '{new_status}'")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'new_status': new_status})
            return redirect('admin_explore')
        return JsonResponse({'status': 'error', 'message': 'Status tidak valid'}, status=400)
    return JsonResponse({'status': 'error'}, status=405)


@admin_login_required
def admin_add_news(request):
    if request.method == 'POST':
        title      = request.POST.get('title', '').strip()
        edition_id = request.POST.get('edition')
        content    = request.POST.get('content', '').strip()
        image_file = request.FILES.get('image_file')
        edition = NewsEdition.objects.filter(edition_id=edition_id).first() if edition_id else None
        if title:
            News.objects.create(
                title=title, edition=edition,
                content=content or None, image_file=image_file or None
            )
            log_admin_activity(f"News '{title}' dibuat")
            return redirect('admin_explore')
    editions = NewsEdition.objects.all()
    return render(request, 'cms/news_form.html', {
        'action': 'Tambah News', 'news': None,
        'editions': editions, 'form_action': 'admin_add_news',
    })


@admin_login_required
def admin_edit_news(request, id):
    news_item = get_object_or_404(News, news_id=id)
    if request.method == 'POST':
        old_title = news_item.title
        news_item.title = request.POST.get('title', '').strip() or news_item.title
        edition_id = request.POST.get('edition')
        if edition_id:
            news_item.edition = NewsEdition.objects.filter(edition_id=edition_id).first()
        news_item.content = request.POST.get('content', '').strip() or news_item.content
        image_file = request.FILES.get('image_file')
        if image_file:
            news_item.image_file = image_file
        news_item.save()
        log_admin_activity(f"News '{old_title}' diperbarui menjadi '{news_item.title}'")
        return redirect('admin_explore')
    editions = NewsEdition.objects.all()
    return render(request, 'cms/news_form.html', {
        'action': 'Edit News', 'news': news_item,
        'editions': editions, 'form_action': 'admin_edit_news',
    })


@admin_login_required
def admin_delete_news(request, id):
    if request.method == 'POST':
        news_item = get_object_or_404(News, news_id=id)
        title = news_item.title
        news_item.delete()
        log_admin_activity(f"News '{title}' dihapus")
    return redirect('admin_explore')


@admin_login_required
def admin_add_attribute(request):
    if request.method == 'POST':
        attribute_name = request.POST.get('attribute_name', '').strip()
        attribute_type = request.POST.get('attribute_type', '').strip()
        file_url = request.POST.get('file_url', '').strip()
        if attribute_name:
            Attribute.objects.create(
                attribute_name=attribute_name,
                attribute_type=attribute_type or None,
                file_url=file_url or None
            )
            log_admin_activity(f"Attribute '{attribute_name}' dibuat")
            return redirect('admin_explore')
    from .models import ATTRIBUTE_TYPES
    return render(request, 'cms/attribute_form.html', {
        'action': 'Tambah Attribute', 'attribute': None,
        'attribute_types': ATTRIBUTE_TYPES, 'form_action': 'admin_add_attribute',
    })


@admin_login_required
def admin_edit_attribute(request, id):
    attribute = get_object_or_404(Attribute, attribute_id=id)
    if request.method == 'POST':
        old_name = attribute.attribute_name
        attribute.attribute_name = request.POST.get('attribute_name', '').strip() or attribute.attribute_name
        attribute.attribute_type = request.POST.get('attribute_type', '').strip() or attribute.attribute_type
        attribute.file_url = request.POST.get('file_url', '').strip() or attribute.file_url
        attribute.save()
        log_admin_activity(f"Attribute '{old_name}' diperbarui menjadi '{attribute.attribute_name}'")
        return redirect('admin_explore')
    from .models import ATTRIBUTE_TYPES
    return render(request, 'cms/attribute_form.html', {
        'action': 'Edit Attribute', 'attribute': attribute,
        'attribute_types': ATTRIBUTE_TYPES, 'form_action': 'admin_edit_attribute',
    })


@admin_login_required
def admin_delete_attribute(request, id):
    if request.method == 'POST':
        attribute = get_object_or_404(Attribute, attribute_id=id)
        name = attribute.attribute_name
        attribute.delete()
        log_admin_activity(f"Attribute '{name}' dihapus")
    return redirect('admin_explore')


@admin_login_required
def feedback_admin(request):
    selected_event = request.GET.get('event', 'all')
    selected_sentiment = request.GET.get('sentiment', 'all')
    page_number = request.GET.get('page', 1)

    event_options = list(Event.objects.order_by('event_name').values_list('event_name', flat=True))

    def build_event_query(event_name):
        tokens = [token.strip() for token in event_name.lower().split() if len(token.strip()) > 2]
        query = None
        for token in tokens:
            q = Q(message__icontains=token)
            query = q if query is None else query | q
        return query

    def detect_event(message):
        text = message.lower()
        for event_name in event_options:
            if not event_name:
                continue
            lower_name = event_name.lower()
            if lower_name in text:
                return event_name
            for token in lower_name.split():
                if len(token) > 2 and token in text:
                    return event_name
        return 'General'

    base_qs = Feedback.objects.order_by('-created_at')

    if selected_event != 'all' and selected_event in event_options:
        query = build_event_query(selected_event)
        if query is not None:
            base_qs = base_qs.filter(query)

    all_feedbacks = list(base_qs)
    total_positive = total_neutral = total_negative = 0
    feedback_entries = []

    for fb in all_feedbacks:
        confidence = None
        try:
            pred_sentiment, confidence = sentiment_analyzer.predict(fb.message)
        except Exception:
            pred_sentiment = 'neutral'
            confidence = 0.50

        if pred_sentiment == 'positive':
            total_positive += 1
        elif pred_sentiment == 'negative':
            total_negative += 1
        else:
            total_neutral += 1

        if selected_sentiment == 'all' or selected_sentiment == pred_sentiment:
            sentiment_text = f"{pred_sentiment.capitalize()} ({round(confidence * 100)}%)"
            fb.sentiment = pred_sentiment
            feedback_entries.append({
                'comment': fb.message,
                'time': fb.created_at.strftime('%d %b %Y %H:%M'),
                'user': fb.session_id or 'Anonymous',
                'event': detect_event(fb.message),
                'sentiment': sentiment_text,
                'rating': fb.rating if fb.rating is not None else 'N/A',
                'platform': fb.source_platform.capitalize(),
                'confidence': confidence,
                'original_obj': fb
            })

    total_feedback = total_positive + total_neutral + total_negative
    if total_feedback:
        positive_percent = round(total_positive / total_feedback * 100)
        neutral_percent  = round(total_neutral  / total_feedback * 100)
        negative_percent = round(total_negative / total_feedback * 100)
    else:
        positive_percent = neutral_percent = negative_percent = 0

    paginator = Paginator(feedback_entries, 10)
    page_obj = paginator.get_page(page_number)

    most_common = sentiment_analyzer.extract_common_words(
        [fb.message for fb in base_qs], limit=8
    )
    most_common_words = [{'word': word, 'count': count} for word, count in most_common]

    context = {
        'feedbacks': page_obj,
        'page_obj': page_obj,
        'selected_event': selected_event,
        'selected_sentiment': selected_sentiment,
        'positive': total_positive,
        'neutral': total_neutral,
        'negative': total_negative,
        'positive_percent': positive_percent,
        'neutral_percent': neutral_percent,
        'negative_percent': negative_percent,
        'event_options': event_options,
        'most_common_words': most_common_words,
    }
    return render(request, 'cms/feedback_admin.html', context)


# =====================
# ATTENDANCE VIEWS
# =====================
from .models import Attendance


def submit_attendance(request, id):
    """Participant self-attendance form (GPS + photo)."""
    event = get_object_or_404(Event, event_id=id)

    # Business rule: attendance only when window is open
    if not event.is_attendance_open:
        return render(request, 'cms/attendance_form.html', {
            'event': event,
            'errors': ['Waktu absensi untuk event ini belum dibuka atau sudah ditutup.'],
        })

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        latitude  = request.POST.get('latitude', '').strip()
        longitude = request.POST.get('longitude', '').strip()
        photo     = request.FILES.get('photo_evidence')

        errors = []
        if not email:
            errors.append('Email wajib diisi.')
        if not latitude or not longitude:
            errors.append('Lokasi GPS wajib diambil sebelum mengirim.')
        if not photo:
            errors.append('Foto bukti kehadiran wajib diunggah.')

        # Check registration exists
        reg = EventRegistration.objects.filter(
            event_id=event.event_id,
            email=email,
        ).first()
        if not errors and not reg:
            errors.append('Email ini tidak terdaftar pada event ini.')

        # Check duplicate attendance
        if not errors and reg:
            already = Attendance.objects.filter(
                event_registration=reg,
                status__in=[Attendance.STATUS_PENDING, Attendance.STATUS_VERIFIED],
            ).exists()
            if already:
                errors.append('Anda sudah melakukan attendance untuk event ini.')

        if errors:
            return render(request, 'cms/attendance_form.html', {
                'event': event, 'errors': errors,
            })

        Attendance.objects.create(
            event_registration=reg,
            participant_email=email,
            photo_evidence=photo,
            latitude=latitude or None,
            longitude=longitude or None,
        )

        # Simpan email ke session supaya status partisipasi di Event Detail
        # ikut terupdate begitu peserta kembali ke halaman tersebut.
        request.session['participant_email'] = email

        return render(request, 'cms/attendance_form.html', {
            'event': event,
            'show_success': True,
            'event_name': event.event_name,
        })

    return render(request, 'cms/attendance_form.html', {'event': event})


def _resolve_period_range(period, year, quarter, month):
    """
    Terjemahkan parameter filter (period + year/quarter/month) dari
    query string menjadi (start_datetime, end_datetime, trunc_function,
    label) yang dipakai untuk memotong queryset berdasarkan tanggal dan
    mengelompokkan hasil agregasi. Dipakai oleh bagian Attendance
    Analytics (Step 8) di halaman gabungan ini.

    period: 'monthly' | 'quarterly' | 'ytd'
    """
    now = timezone.now()
    year = int(year) if year else now.year

    if period == 'quarterly':
        quarter = int(quarter) if quarter else ((now.month - 1) // 3) + 1
        start_month = (quarter - 1) * 3 + 1
        start = datetime(year, start_month, 1, tzinfo=now.tzinfo)
        end_month = start_month + 2
        if end_month == 12:
            end = datetime(year, 12, 31, 23, 59, 59, tzinfo=now.tzinfo)
        else:
            end = datetime(year, end_month + 1, 1, tzinfo=now.tzinfo) - timedelta(seconds=1)
        trunc = TruncMonth
        label = f"Q{quarter} {year}"

    elif period == 'ytd':
        start = datetime(year, 1, 1, tzinfo=now.tzinfo)
        end = now if year == now.year else datetime(year, 12, 31, 23, 59, 59, tzinfo=now.tzinfo)
        trunc = TruncMonth
        label = f"YTD {year}"

    else:  # 'monthly' (default)
        month = int(month) if month else now.month
        start = datetime(year, month, 1, tzinfo=now.tzinfo)
        if month == 12:
            end = datetime(year, 12, 31, 23, 59, 59, tzinfo=now.tzinfo)
        else:
            end = datetime(year, month + 1, 1, tzinfo=now.tzinfo) - timedelta(seconds=1)
        trunc = TruncDay
        label = start.strftime('%B %Y')

    return start, end, trunc, label


@admin_login_required
def admin_attendance_list(request):
    """
    Halaman gabungan "Attendance" di admin — digabung jadi satu page:
      1) Attendance Verification (tabel + aksi verify/reject — sudah ada)
      2) Attendance Analytics (Step 8 — KPI + chart, filter periode)
      3) Participation Analytics (Step 9 — growth peserta, filter granularitas)

    Semua query string filter dipisah prefix-nya agar tidak bertabrakan:
      - status            -> filter tabel verifikasi
      - period/year/quarter/month       -> filter Attendance Analytics
      - granularity/p_year              -> filter Participation Analytics
    """
    # ---------- 1) ATTENDANCE VERIFICATION (tabel) ----------
    current_status = request.GET.get('status', '').strip()

    qs = Attendance.objects.select_related('event_registration').order_by('-attendance_timestamp')
    if current_status:
        qs = qs.filter(status=current_status)

    summary = {
        'total':    Attendance.objects.count(),
        'pending':  Attendance.objects.filter(status=Attendance.STATUS_PENDING).count(),
        'verified': Attendance.objects.filter(status=Attendance.STATUS_VERIFIED).count(),
        'rejected': Attendance.objects.filter(status=Attendance.STATUS_REJECTED).count(),
    }

    # ---------- 2) ATTENDANCE ANALYTICS (Step 8) ----------
    period  = request.GET.get('period', 'monthly')
    year    = request.GET.get('year')
    quarter = request.GET.get('quarter')
    month   = request.GET.get('month')

    period_start, period_end, period_trunc, period_label = _resolve_period_range(period, year, quarter, month)

    registrations_qs = EventRegistration.objects.filter(
        registered_at__range=(period_start, period_end)
    )
    attendance_period_qs = Attendance.objects.filter(
        attendance_timestamp__range=(period_start, period_end)
    )

    total_registrations = registrations_qs.count()
    total_attendance_period = attendance_period_qs.count()
    verified_attendance_period = attendance_period_qs.filter(status=Attendance.STATUS_VERIFIED).count()
    pending_attendance_period  = attendance_period_qs.filter(status=Attendance.STATUS_PENDING).count()
    rejected_attendance_period = attendance_period_qs.filter(status=Attendance.STATUS_REJECTED).count()

    if total_registrations:
        attendance_rate = round((total_attendance_period / total_registrations) * 100, 1)
        no_show_rate = round(
            ((total_registrations - total_attendance_period) / total_registrations) * 100, 1
        )
    else:
        attendance_rate = 0
        no_show_rate = 0

    attendance_series_qs = (
        attendance_period_qs
        .annotate(period_bucket=period_trunc('attendance_timestamp'))
        .values('period_bucket')
        .annotate(count=Count('attendance_id'))
        .order_by('period_bucket')
    )
    attendance_chart_labels = [
        row['period_bucket'].strftime('%d %b') if period_trunc is TruncDay else row['period_bucket'].strftime('%b %Y')
        for row in attendance_series_qs
    ]
    attendance_chart_values = [row['count'] for row in attendance_series_qs]

    # ---------- 3) PARTICIPATION ANALYTICS (Step 9) ----------
    granularity = request.GET.get('granularity', 'monthly')  # monthly | quarterly | yearly
    p_year = request.GET.get('p_year')
    p_year = int(p_year) if p_year else timezone.now().year

    if granularity == 'yearly':
        p_trunc = TruncYear
        p_date_fmt = '%Y'
        participation_qs = EventRegistration.objects.all()
    elif granularity == 'quarterly':
        p_trunc = TruncQuarter
        p_date_fmt = None  # diformat manual di bawah
        participation_qs = EventRegistration.objects.filter(registered_at__year=p_year)
    else:
        p_trunc = TruncMonth
        p_date_fmt = '%b %Y'
        participation_qs = EventRegistration.objects.filter(registered_at__year=p_year)

    participation_series = list(
        participation_qs
        .annotate(bucket=p_trunc('registered_at'))
        .values('bucket')
        .annotate(count=Count('registration_id'))
        .order_by('bucket')
    )

    participation_labels = []
    participation_values = []
    for row in participation_series:
        bucket = row['bucket']
        if granularity == 'quarterly':
            q_num = (bucket.month - 1) // 3 + 1
            participation_labels.append(f"Q{q_num} {bucket.year}")
        else:
            participation_labels.append(bucket.strftime(p_date_fmt))
        participation_values.append(row['count'])

    growth_percent = None
    if len(participation_values) >= 2 and participation_values[-2] > 0:
        growth_percent = round(
            ((participation_values[-1] - participation_values[-2]) / participation_values[-2]) * 100, 1
        )
    elif len(participation_values) >= 2 and participation_values[-2] == 0 and participation_values[-1] > 0:
        growth_percent = 100.0

    total_participants = sum(participation_values)

    # ---------- CONTEXT GABUNGAN ----------
    context = {
        # Attendance Verification
        'attendances':    qs,
        'summary':        summary,
        'current_status': current_status,
        'status_choices': Attendance.STATUS_CHOICES,

        # Attendance Analytics (Step 8)
        'period': period,
        'period_label': period_label,
        'selected_year': int(year) if year else timezone.now().year,
        'selected_quarter': int(quarter) if quarter else None,
        'selected_month': int(month) if month else None,
        'attendance_kpi': {
            'total_registrations': total_registrations,
            'total_attendance': total_attendance_period,
            'verified_attendance': verified_attendance_period,
            'pending_attendance': pending_attendance_period,
            'rejected_attendance': rejected_attendance_period,
            'attendance_rate': attendance_rate,
            'no_show_rate': no_show_rate,
        },
        'attendance_chart_labels': json.dumps(attendance_chart_labels),
        'attendance_chart_values': json.dumps(attendance_chart_values),
        'year_choices': range(timezone.now().year - 3, timezone.now().year + 1),
        'quarter_choices': [1, 2, 3, 4],
        'month_choices': list(enumerate(
            ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
             'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'],
            start=1
        )),

        # Participation Analytics (Step 9)
        'granularity': granularity,
        'selected_p_year': p_year,
        'participation_labels': json.dumps(participation_labels),
        'participation_values': json.dumps(participation_values),
        'total_participants': total_participants,
        'growth_percent': growth_percent,
        'latest_period_label': participation_labels[-1] if participation_labels else None,
        'latest_period_count': participation_values[-1] if participation_values else 0,
    }
    return render(request, 'cms/admin_attendance_list.html', context)


@admin_login_required
def admin_verify_attendance(request, attendance_id):
    if request.method == 'POST':
        att = get_object_or_404(Attendance, attendance_id=attendance_id)
        att.status = Attendance.STATUS_VERIFIED
        att.verified_at = timezone.now()
        att.save()
        log_admin_activity(f"Attendance #{attendance_id} ({att.participant_email}) diverifikasi")
    return redirect('admin_attendance')


@admin_login_required
def admin_reject_attendance(request, attendance_id):
    if request.method == 'POST':
        att = get_object_or_404(Attendance, attendance_id=attendance_id)
        att.status = Attendance.STATUS_REJECTED
        att.save()
        log_admin_activity(f"Attendance #{attendance_id} ({att.participant_email}) ditolak")
    return redirect('admin_attendance')