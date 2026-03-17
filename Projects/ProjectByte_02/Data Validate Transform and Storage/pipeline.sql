drop table if exists BreadCrumb;
drop table if exists Trip;
drop type if exists service_type;
drop type if exists tripdir_type;

create type service_type as enum ('Weekday', 'Saturday', 'Sunday');
create type tripdir_type as enum ('Out', 'Back');

create table Trip (
        trip_id integer,
        route_id integer,
        vehicle_id integer,
        service_key service_type,
        direction tripdir_type,
        PRIMARY KEY (trip_id)
);

create table BreadCrumb (
        tstamp timestamp,
        latitude float,
        longitude float,
        speed float,
        trip_id integer,
        FOREIGN KEY (trip_id) REFERENCES Trip
);
