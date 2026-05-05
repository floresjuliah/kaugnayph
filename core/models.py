from django.db import models


class Users(models.Model):
    userid = models.AutoField(db_column='UserID', primary_key=True)
    username = models.CharField(db_column='Username', max_length=50, unique=True)
    password = models.CharField(db_column='Password', max_length=255)

    firstname = models.CharField(db_column='Firstname', max_length=100, blank=True, null=True)
    lastname = models.CharField(db_column='Lastname', max_length=100, blank=True, null=True)
    middlename = models.CharField(db_column='Middlename', max_length=100, blank=True, null=True)

    contactno = models.CharField(db_column='ContactNo', max_length=20, unique=True, blank=True, null=True)
    sex = models.CharField(db_column='Sex', max_length=10, blank=True, null=True)

    is_verified = models.IntegerField(blank=True, null=True)
    is_active = models.IntegerField(blank=True, null=True)

    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'Users'
        managed = False


class Announcementcategories(models.Model):
    acid = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'AnnouncementCategories'
        managed = False


class Announcements(models.Model):
    announcement_id = models.AutoField(db_column='Announcement_id', primary_key=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    content = models.TextField(blank=True, null=True)

    category = models.ForeignKey(
        Announcementcategories,
        models.DO_NOTHING,
        db_column='category_id',
        blank=True,
        null=True
    )

    file = models.BinaryField(db_column='File', blank=True, null=True)

    posted_by = models.ForeignKey(
        Users,
        models.DO_NOTHING,
        db_column='posted_by',
        blank=True,
        null=True
    )

    send_sms = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'Announcements'
        managed = False

class Announcementfeedback(models.Model):
    afid = models.AutoField(db_column='AFID', primary_key=True)

    announcement = models.ForeignKey(
        Announcements,
        models.DO_NOTHING,
        db_column='announcement_id'
    )

    user = models.ForeignKey(
        Users,
        models.DO_NOTHING,
        db_column='user_id'
    )

    rating = models.IntegerField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'AnnouncementFeedback'
        managed = False
        unique_together = (('announcement', 'user'),)

class Auditlogs(models.Model):
    logid = models.AutoField(db_column='LogID', primary_key=True)

    user = models.ForeignKey(
        Users,
        models.DO_NOTHING,
        db_column='user_id',
        blank=True,
        null=True
    )

    action = models.CharField(max_length=100)
    module_name = models.CharField(max_length=50, blank=True, null=True)
    table_name = models.CharField(max_length=100, blank=True, null=True)
    record_id = models.IntegerField(blank=True, null=True)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    ip_address = models.CharField(max_length=50, blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'AuditLogs'
        managed = False

class SmsOutbox(models.Model):
    outboxid = models.AutoField(db_column='OutboxID', primary_key=True)
    recipient_number = models.CharField(max_length=20, blank=True, null=True)
    message = models.TextField(blank=True, null=True)

    sent_by = models.ForeignKey(
        Users,
        models.DO_NOTHING,
        db_column='sent_by',
        blank=True,
        null=True
    )

    sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'SMS_Outbox'
        managed = False

class Complainttype(models.Model):
    ctid = models.AutoField(db_column='CTID', primary_key=True)
    type = models.CharField(db_column='Type', max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'ComplaintType'
        managed = False

class Complaints(models.Model):
    complaintsid = models.AutoField(db_column='ComplaintsID', primary_key=True)

    complaint_type = models.ForeignKey(
        Complainttype,
        models.DO_NOTHING,
        db_column='complaint_type_id',
        blank=True,
        null=True
    )

    complainant_user = models.ForeignKey(
        Users,
        models.DO_NOTHING,
        db_column='complainant_user_id',
        blank=True,
        null=True
    )

    complainee = models.CharField(max_length=255, blank=True, null=True)
    title = models.CharField(db_column='Title', max_length=255, blank=True, null=True)
    description = models.TextField(db_column='Description', blank=True, null=True)
    file = models.BinaryField(db_column='File', blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    dateadded = models.DateTimeField(db_column='DateAdded', blank=True, null=True)
    datefinish = models.DateTimeField(db_column='DateFinish', blank=True, null=True)

    handled_by = models.ForeignKey(
        Users,
        models.DO_NOTHING,
        db_column='handled_by',
        related_name='complaints_handled_by_set',
        blank=True,
        null=True
    )

    class Meta:
        db_table = 'Complaints'
        managed = False

